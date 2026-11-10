"""Local data-control checks for AI coding tools.

Every check reads files on this machine (and the process environment) only.
Nothing is sent anywhere. Each finding cites the vendor doc for the setting."""
import json
import os
import pathlib
import sqlite3

from . import accounts
from .util import app_config_dir, dig, load_jsonc, load_toml, platform_name, truthy

CC_DOC = "https://code.claude.com/docs/en/data-usage"
CODEX_DOC = "https://developers.openai.com/codex/config-reference"
GEM_DOC = "https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md"
VSC_DOC = "https://code.visualstudio.com/docs/configure/telemetry"
CURSOR_DOC = "https://cursor.com/data-use"
AIDER_DOC = "https://aider.chat/docs/more/analytics.html"

STATUS_RANK = {"ok": 0, "info": 0, "unknown": 1, "unverified": 1, "stale": 1, "warn": 2, "bad": 3}


class Ctx:
    def __init__(self, home=None, env=None, cwd=None, plat=None, max_age=14):
        self.home = home or os.path.expanduser("~")
        self.env = dict(os.environ if env is None else env)
        self.cwd = cwd or os.getcwd()
        self.plat = plat or platform_name()
        self.max_age = max_age
        self.attest = accounts.load(self.home)


def F(id, tool, title, status, value, source="", detail="", fix=None, doc=""):
    return {"id": id, "tool": tool, "title": title, "status": status, "value": value,
            "source": source, "detail": detail, "fix": fix, "doc": doc}


def _short(ctx, path):
    if path and path.startswith(ctx.home + os.sep):
        return "~" + path[len(ctx.home):]
    return path


def account_finding(ctx, vendor, tool, why_prefix):
    st, detail = accounts.status(vendor, ctx.max_age, data=ctx.attest)
    a = accounts.ACCOUNTS[vendor]
    status = {"ok": "ok", "bad": "bad", "stale": "stale", "unverified": "unverified"}[st]
    return F(f"{vendor}.account-training", tool, "account: train on my data", status,
             {"ok": "off (attested)", "bad": "ON (attested)"}.get(st, "can't read locally"),
             a["url"], f"{why_prefix} {detail}. {a['setting']}.",
             None if st == "ok" else f"open {a['url']}, set it to {a['off_means']}, then: optout attest {vendor} off",
             a["evidence"])


# --------------------------------------------------------------------- Claude Code
def _claude_dirs(ctx):
    base = ctx.env.get("CLAUDE_CONFIG_DIR") or os.path.join(ctx.home, ".claude")
    return base, os.path.join(ctx.home, ".claude.json")


def claude_managed_paths(plat):
    if plat == "mac":
        return ["/Library/Application Support/ClaudeCode/managed-settings.json"]
    if plat == "windows":
        return [r"C:\Program Files\ClaudeCode\managed-settings.json"]
    return ["/etc/claude-code/managed-settings.json"]


def claude_code(ctx):
    base, cj = _claude_dirs(ctx)
    if not (os.path.isdir(base) or os.path.exists(cj)):
        return []
    out = []
    layers = []  # (label, env-dict, settings) lowest -> highest
    user_path = os.path.join(base, "settings.json")
    user, err = load_jsonc(user_path)
    if err:
        out.append(F("claude.settings", "Claude Code", "settings file", "warn", "unreadable",
                     _short(ctx, user_path), err, doc=CC_DOC))
    layers.append((_short(ctx, user_path), (user or {}).get("env") or {}, user or {}))
    for mp in claude_managed_paths(ctx.plat):
        m, _ = load_jsonc(mp)
        if m:
            layers.append((mp + " (managed)", m.get("env") or {}, m))
    env_src = {}
    for label, env, _ in layers:
        for k, v in env.items():
            env_src[k] = (str(v), label)
    for k, v in ctx.env.items():  # the shell environment wins over settings env blocks
        if k.startswith(("DISABLE_", "CLAUDE_CODE_", "DO_NOT_TRACK", "OTEL_", "ANTHROPIC_API_KEY")):
            env_src[k] = (v, "shell environment")

    def on(name):
        v = env_src.get(name)
        return (truthy(v[0]), v[1]) if v else (False, None)

    third_party = [p for p in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
                               "CLAUDE_CODE_USE_ANTHROPIC_AWS") if on(p)[0]]

    def flag(id, title, var, default_detail, also=()):
        for cand in (var, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC") + tuple(also):
            set_, src = on(cand)
            if set_:
                return F(id, "Claude Code", title, "ok", f"off ({cand}=1)", src, doc=CC_DOC)
        if third_party:
            return F(id, "Claude Code", title, "ok", f"off by default ({third_party[0]})", "provider default", doc=CC_DOC)
        return F(id, "Claude Code", title, "warn", "on (default)", "not set", default_detail,
                 f"optout fix  (sets {var}=1 in ~/.claude/settings.json env)", CC_DOC)

    out.append(flag("claude.telemetry", "usage metrics", "DISABLE_TELEMETRY",
                    "Latency/usage metrics go to Anthropic and third-party logging (no code or prompts)."))
    out.append(flag("claude.error-reports", "error reports", "DISABLE_ERROR_REPORTING",
                    "Stack traces go to a third-party error tracker (Pro/Max/Ultra sign-ins, v2.1.198+)."))
    out.append(flag("claude.feedback", "/feedback, /bug, /share uploads", "DISABLE_FEEDBACK_COMMAND",
                    "One /bug sends the conversation incl. code to Anthropic; kept 5 years."))
    out.append(flag("claude.survey", "session survey transcript upload", "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
                    "A 'Yes' on the follow-up uploads transcripts, subagent transcripts and session logs (kept up to 6 months).",
                    also=("DISABLE_TELEMETRY", "DO_NOT_TRACK")))
    otel_prompts, src = on("OTEL_LOG_USER_PROMPTS")
    if on("CLAUDE_CODE_ENABLE_TELEMETRY")[0]:
        ep = env_src.get("OTEL_EXPORTER_OTLP_ENDPOINT", ("(unset)", ""))[0]
        out.append(F("claude.otel", "Claude Code", "OpenTelemetry export", "warn" if otel_prompts else "info",
                     ("prompts included -> " if otel_prompts else "metrics/events -> ") + ep,
                     src or env_src.get("CLAUDE_CODE_ENABLE_TELEMETRY")[1],
                     "OTEL_LOG_USER_PROMPTS=1 exports raw prompt text to the collector." if otel_prompts else "",
                     doc="https://code.claude.com/docs/en/monitoring-usage"))
    days = None
    for label, _, s in layers:
        if "cleanupPeriodDays" in s:
            days, dsrc = s["cleanupPeriodDays"], label
    out.append(F("claude.transcripts", "Claude Code", "local transcript retention", "info",
                 f"{days if days is not None else 30} days" + ("" if days is not None else " (default)"),
                 dsrc if days is not None else "~/.claude/projects/",
                 "Plaintext transcripts kept on disk for session resume.", doc=CC_DOC))
    # account type
    cjd, _ = load_jsonc(cj)
    acct = (cjd or {}).get("oauthAccount") if isinstance(cjd, dict) else None
    if third_party or (env_src.get("ANTHROPIC_API_KEY") and not acct):
        out.append(F("claude.account-training", "Claude Code", "account: train on my data", "ok",
                     "commercial terms", third_party[0] if third_party else "ANTHROPIC_API_KEY",
                     "API / cloud-provider traffic is not trained on unless you opt in.", doc=CC_DOC))
    elif acct:
        who = acct.get("emailAddress") or "claude.ai account"
        org = acct.get("organizationName")
        out.append(account_finding(ctx, "claude", "Claude Code",
                                   f"Signed in as {who}{' (' + org + ')' if org else ''}. If this is Free/Pro/Max/Ultra the "
                                   "account toggle decides training;"))
    return out


# --------------------------------------------------------------------- Codex
def codex(ctx):
    home = ctx.env.get("CODEX_HOME") or os.path.join(ctx.home, ".codex")
    if not os.path.isdir(home):
        return []
    out = []
    cfg_path = os.path.join(home, "config.toml")
    cfg, err = load_toml(cfg_path)
    cfg = cfg or {}
    src = _short(ctx, cfg_path)
    if err:
        out.append(F("codex.config", "Codex", "config.toml", "warn", "parse problem", src, err, doc=CODEX_DOC))
    an = dig(cfg, "analytics.enabled")
    if an is False:
        out.append(F("codex.analytics", "Codex", "analytics (Statsig metrics)", "ok", "off (analytics.enabled = false)", src, doc=CODEX_DOC))
    else:
        out.append(F("codex.analytics", "Codex", "analytics (Statsig metrics)", "warn",
                     "on (analytics.enabled = true)" if an else "client default (unset)", src if an else "not set",
                     "Built-in metrics exporter follows analytics.enabled.", "optout fix  (sets [analytics] enabled = false)", CODEX_DOC))
    fb = dig(cfg, "feedback.enabled")
    if fb is False:
        out.append(F("codex.feedback", "Codex", "/feedback uploads", "ok", "off (feedback.enabled = false)", src, doc=CODEX_DOC))
    else:
        out.append(F("codex.feedback", "Codex", "/feedback uploads", "warn", "on" + ("" if fb else " (default)"),
                     src if fb else "not set", "feedback.enabled defaults to true.",
                     "optout fix  (sets [feedback] enabled = false)", CODEX_DOC))
    persist = dig(cfg, "history.persistence") or "save-all"
    out.append(F("codex.history", "Codex", "local prompt history", "info",
                 f"{persist}" + ("" if dig(cfg, "history.persistence") else " (default)"), "~/.codex/history.jsonl",
                 "history.persistence = \"none\" stops saving it.", doc=CODEX_DOC))
    if dig(cfg, "otel.log_user_prompt") is True:
        out.append(F("codex.otel-prompts", "Codex", "OpenTelemetry prompt export", "warn", "raw prompts exported",
                     src, f"otel.exporter = {dig(cfg, 'otel.exporter')!r}", doc=CODEX_DOC))
    auth, _ = load_jsonc(os.path.join(home, "auth.json"))
    if isinstance(auth, dict):
        mode = str(auth.get("auth_mode") or "").lower()
        if mode == "chatgpt" or (not mode and auth.get("tokens")):
            out.append(account_finding(ctx, "chatgpt", "Codex", "Signed in with ChatGPT, so the ChatGPT data control decides training;"))
        elif mode in ("apikey", "api_key") or auth.get("OPENAI_API_KEY"):
            out.append(F("codex.account-training", "Codex", "account: train on my data", "ok", "API key",
                         "~/.codex/auth.json", "OpenAI API data is not used for training by default.",
                         doc="https://platform.openai.com/docs/guides/your-data"))
    return out


# --------------------------------------------------------------------- Gemini CLI
def gemini_system_path(plat):
    if plat == "mac":
        return "/Library/Application Support/GeminiCli/settings.json"
    if plat == "windows":
        return r"C:\ProgramData\gemini-cli\settings.json"
    return "/etc/gemini-cli/settings.json"


def gemini(ctx):
    user_path = os.path.join(ctx.home, ".gemini", "settings.json")
    if not os.path.isdir(os.path.dirname(user_path)):
        return []
    layers = []
    for p in (user_path, os.path.join(ctx.cwd, ".gemini", "settings.json"), gemini_system_path(ctx.plat)):
        d, err = load_jsonc(p)
        if d:
            layers.append((_short(ctx, p), d))

    def get(*keys):
        val, src = None, None
        for label, d in layers:
            for k in keys:
                v = dig(d, k)
                if v is not None:
                    val, src = v, label
        return val, src

    out = []
    us, src = get("usageStatisticsEnabled", "privacy.usageStatisticsEnabled")
    if us is False:
        out.append(F("gemini.usage-stats", "Gemini CLI", "usage statistics", "ok", "off (privacy.usageStatisticsEnabled)", src, doc=GEM_DOC))
    else:
        out.append(F("gemini.usage-stats", "Gemini CLI", "usage statistics", "warn", "on" + ("" if us else " (default)"),
                     src or "not set", "Defaults to true.", "optout fix  (sets privacy.usageStatisticsEnabled = false)", GEM_DOC))
    tel, tsrc = get("telemetry.enabled")
    if "GEMINI_TELEMETRY_ENABLED" in ctx.env:
        tel, tsrc = ctx.env["GEMINI_TELEMETRY_ENABLED"] in ("true", "1"), "shell environment"
    if tel:
        lp, _ = get("telemetry.logPrompts")
        if "GEMINI_TELEMETRY_LOG_PROMPTS" in ctx.env:
            lp = ctx.env["GEMINI_TELEMETRY_LOG_PROMPTS"] in ("true", "1")
        target = ctx.env.get("GEMINI_TELEMETRY_TARGET") or get("telemetry.target")[0] or "local"
        out.append(F("gemini.telemetry", "Gemini CLI", "OpenTelemetry", "warn" if lp is not False else "info",
                     f"on, target={target}, logPrompts={'false' if lp is False else 'true/default'}", tsrc,
                     f"Prompt text is sent to your telemetry target ({target}) unless telemetry.logPrompts = false (default true).", doc=GEM_DOC))
    auth, asrc = get("security.auth.selectedType", "selectedAuthType")
    if auth == "gemini-api-key":
        out.append(F("gemini.auth", "Gemini CLI", "auth: Gemini API key", "warn", "gemini-api-key", asrc,
                     "On the unpaid tier, the Gemini API terms let Google use prompts and responses to improve "
                     "products, with human review. Paid (billing-enabled) keys are not used that way.",
                     "use a billing-enabled key or Vertex AI", "https://ai.google.dev/gemini-api/terms"))
    elif auth == "oauth-personal":
        out.append(F("gemini.auth", "Gemini CLI", "auth: personal Google login", "info", "oauth-personal", asrc,
                     "Google stopped serving consumer Code Assist tiers in Gemini CLI on Jun 18 2026.",
                     doc="https://developers.google.com/gemini-code-assist/resources/privacy-notice-gemini-code-assist-individuals"))
    elif auth:
        out.append(F("gemini.auth", "Gemini CLI", "auth", "info", str(auth), asrc, doc=GEM_DOC))
    return out


# --------------------------------------------------------------------- VS Code family + Cursor
EDITORS = [("Code", "VS Code"), ("Code - Insiders", "VS Code Insiders"), ("VSCodium", "VSCodium"),
           ("Cursor", "Cursor"), ("Windsurf", "Windsurf")]

PRIVACY_OK = {"NO_STORAGE": "Privacy Mode (legacy no-storage)", "NO_TRAINING": "Privacy Mode (no training)"}


def cursor_privacy(ctx, base):
    db = os.path.join(base, "User", "globalStorage", "state.vscdb")
    if not os.path.exists(db):
        return None
    keys = ("cursorai/donotchange/privacyMode", "cursorai/donotchange/newPrivacyMode2",
            "cursorai/donotchange/partnerDataShare")
    vals = {}
    try:
        con = sqlite3.connect(pathlib.Path(db).as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            for k in keys:
                row = con.execute("SELECT value FROM ItemTable WHERE key = ?", (k,)).fetchone()
                if row:
                    v = row[0]
                    vals[k.rsplit("/", 1)[1]] = v.decode() if isinstance(v, bytes) else v
        finally:
            con.close()
    except sqlite3.Error as e:
        return [F("cursor.privacy-mode", "Cursor", "Privacy Mode (cached)", "unknown", "unreadable",
                  _short(ctx, db), str(e), doc=CURSOR_DOC)]
    out = []
    mode = None
    raw2 = vals.get("newPrivacyMode2")
    if raw2:
        try:
            mode = json.loads(raw2).get("privacyMode")
        except (ValueError, AttributeError):
            mode = None
    legacy = vals.get("privacyMode")
    src = _short(ctx, db)
    if mode:
        short = str(mode).replace("PRIVACY_MODE_", "")
        if short in PRIVACY_OK:
            f = F("cursor.privacy-mode", "Cursor", "Privacy Mode (cached from account)", "ok",
                  f"{PRIVACY_OK[short]} [{mode}]", src,
                  "Strongest mode; reportedly can't be re-enabled once you leave it." if short == "NO_STORAGE"
                  else "No training; Cursor may still store code for features like Cloud Agents.", doc=CURSOR_DOC)
            f["strength"] = 2 if short == "NO_STORAGE" else 1
            out.append(f)
        elif "TRAINING" in short or "USAGE" in short or "SHARE" in short:
            out.append(F("cursor.privacy-mode", "Cursor", "Privacy Mode (cached from account)", "bad",
                         f"OFF: data sharing [{mode}]", src,
                         "Cursor may store and train on code and prompts.",
                         "Cursor Settings > General > Privacy Mode", CURSOR_DOC))
        else:
            out.append(F("cursor.privacy-mode", "Cursor", "Privacy Mode (cached from account)", "unknown",
                         str(mode), src, "Unrecognised value; check Cursor Settings.", doc=CURSOR_DOC))
    elif legacy is not None:
        st = "ok" if truthy(legacy) else "bad"
        out.append(F("cursor.privacy-mode", "Cursor", "Privacy Mode (cached from account)", st,
                     "on (legacy flag)" if st == "ok" else "OFF (legacy flag)", src, doc=CURSOR_DOC))
    else:
        out.append(F("cursor.privacy-mode", "Cursor", "Privacy Mode (cached from account)", "unknown",
                     "not cached (not signed in?)", src, doc=CURSOR_DOC))
    if "partnerDataShare" in vals and truthy(vals["partnerDataShare"]):
        out.append(F("cursor.partner-share", "Cursor", "partner data sharing", "bad", "on", src,
                     "Shares data with model partners.", "Cursor Settings > Privacy", CURSOR_DOC))
    return out


def editors(ctx):
    out = []
    for app, label in EDITORS:
        base = app_config_dir(ctx.home, app, ctx.plat)
        if not os.path.isdir(base):
            continue
        sp = os.path.join(base, "User", "settings.json")
        s, err = load_jsonc(sp)
        s = s or {}
        lvl = s.get("telemetry.telemetryLevel")
        if lvl is None and s.get("telemetry.enableTelemetry") is False:
            lvl = "off"
        src = _short(ctx, sp)
        if err:
            out.append(F(f"{app.lower()}.settings", label, "settings.json", "warn", "unreadable", src, err, doc=VSC_DOC))
        if lvl == "off":
            out.append(F(f"{app.lower()}.telemetry", label, "editor telemetry", "ok", "off", src, doc=VSC_DOC))
        else:
            out.append(F(f"{app.lower()}.telemetry", label, "editor telemetry", "warn" if lvl in (None, "all") else "info",
                         (lvl or "all") + ("" if lvl else " (default)"), src if lvl else "not set",
                         "telemetry.telemetryLevel: all | error | crash | off", 'optout fix  (sets "telemetry.telemetryLevel": "off")', VSC_DOC))
        if app == "Cursor":
            out.extend(cursor_privacy(ctx, base) or [])
        ext_dir = os.path.join(ctx.home, {"Code": ".vscode", "Code - Insiders": ".vscode-insiders", "VSCodium": ".vscode-oss",
                                          "Cursor": ".cursor", "Windsurf": ".windsurf"}[app], "extensions")
        try:
            has_copilot = any(n.lower().startswith("github.copilot") for n in os.listdir(ext_dir))
        except OSError:
            has_copilot = False
        if has_copilot and not any(f["id"] == "copilot.account-training" for f in out):
            out.append(account_finding(ctx, "copilot", "GitHub Copilot",
                                       f"Copilot extension installed in {label}. On individual plans the GitHub account setting decides training;"))
    return out


# --------------------------------------------------------------------- Aider
def aider(ctx):
    p = os.path.join(ctx.home, ".aider", "analytics.json")
    d, _ = load_jsonc(p)
    if d is None:
        return []
    src = _short(ctx, p)
    if d.get("permanently_disable"):
        return [F("aider.analytics", "Aider", "analytics", "ok", "off (permanently_disable)", src, doc=AIDER_DOC)]
    if d.get("asked_opt_in"):
        return [F("aider.analytics", "Aider", "analytics", "warn", "on (you opted in)", src,
                  "Usage events go to PostHog.", "optout fix  (sets permanently_disable)", AIDER_DOC)]
    return [F("aider.analytics", "Aider", "analytics", "ok", "off (never opted in)", src, doc=AIDER_DOC)]


# --------------------------------------------------------------------- accounts not tied to a local tool
def standalone_accounts(ctx, seen):
    out = []
    for vendor, tool in (("chatgpt", "ChatGPT"), ("claude", "Claude"), ("gemini", "Gemini apps"),
                         ("copilot", "GitHub Copilot"), ("mistral", "Mistral Le Chat")):
        if f"{vendor}.account-training" in seen:
            continue
        if vendor in ctx.attest:
            out.append(account_finding(ctx, vendor, tool, "Tracked account;"))
    return out


TOOLS = {"claude": claude_code, "codex": codex, "gemini": gemini, "editors": editors, "aider": aider}


def scan(ctx, only=None):
    findings = []
    for name, fn in TOOLS.items():
        if only and name not in only:
            continue
        findings.extend(fn(ctx))
    seen = {f["id"] for f in findings}
    if not only or "accounts" in only:
        findings.extend(standalone_accounts(ctx, seen))
    return findings


def worst(findings):
    return max((STATUS_RANK.get(f["status"], 0) for f in findings), default=0)
