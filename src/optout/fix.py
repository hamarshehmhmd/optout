"""Write the local opt-outs that vendors document. Dry run unless write=True.

Only touches user-level config files of tools that are installed, keeps a
timestamped backup of each file it changes, and never edits Cursor's state DB
or anything server-side."""
import datetime as _dt
import json
import os
import re
import shutil

from .checks import EDITORS, _claude_dirs
from .util import app_config_dir, strip_jsonc

CLAUDE_ENV = ["DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING", "DISABLE_FEEDBACK_COMMAND",
              "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY"]


def toml_set(text, table, key, literal):
    """Set table.key = literal in TOML text, editing in place (keeps comments)."""
    lines = text.splitlines()
    header_re = re.compile(r"^\s*\[\s*" + re.escape(table) + r"\s*\]\s*(#.*)?$")
    any_header = re.compile(r"^\s*\[")
    dotted = re.compile(r"^(\s*)" + re.escape(table) + r"\." + re.escape(key) + r"\s*=.*$")
    plain = re.compile(r"^(\s*)" + re.escape(key) + r"\s*=.*$")
    # dotted key at top level (before the first header)
    for i, ln in enumerate(lines):
        if any_header.match(ln):
            break
        m = dotted.match(ln)
        if m:
            lines[i] = f"{m.group(1)}{table}.{key} = {literal}"
            return "\n".join(lines) + "\n"
    for i, ln in enumerate(lines):
        if header_re.match(ln):
            j = i + 1
            while j < len(lines) and not any_header.match(lines[j]):
                m = plain.match(lines[j])
                if m:
                    lines[j] = f"{m.group(1)}{key} = {literal}"
                    return "\n".join(lines) + "\n"
                j += 1
            lines.insert(i + 1, f"{key} = {literal}")
            return "\n".join(lines) + "\n"
    body = "\n".join(lines).rstrip("\n")
    return (body + "\n\n" if body else "") + f"[{table}]\n{key} = {literal}\n"


def jsonc_set_flat(text, key, value):
    """Set a top-level key in a JSON-with-comments object, keeping comments."""
    lit = json.dumps(value)
    pat = re.compile(r'("' + re.escape(key) + r'"\s*:\s*)("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)')
    if pat.search(text):
        return pat.sub(lambda m: m.group(1) + lit, text, count=1)
    if not text.strip():
        return "{\n    " + json.dumps(key) + ": " + lit + "\n}\n"
    i = text.index("{")
    rest_empty = strip_jsonc(text[i + 1:]).strip() == "}"
    ins = "\n    " + json.dumps(key) + ": " + lit + ("" if rest_empty else ",")
    return text[:i + 1] + ins + text[i + 1:]


class Plan:
    def __init__(self):
        self.changes = []  # dicts: path, tool, what, new_text
        self.skipped = []

    def add(self, path, tool, what, old, new):
        if old != new:
            self.changes.append({"path": path, "tool": tool, "what": what, "old": old, "new": new})


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def plan(home, env=None, plat=None, only=None):
    env = dict(os.environ if env is None else env)
    p = Plan()

    class _C:
        pass
    c = _C(); c.home = home; c.env = env
    want = (lambda n: not only or n in only)

    if want("claude"):
        base, cj = _claude_dirs(c)
        if os.path.isdir(base) or os.path.exists(cj):
            path = os.path.join(base, "settings.json")
            old = _read(path)
            try:
                data = json.loads(old) if old.strip() else {}
            except ValueError:
                p.skipped.append((path, "not valid JSON; fix it first (Claude Code requires strict JSON)"))
            else:
                envb = data.setdefault("env", {})
                added = [k for k in CLAUDE_ENV if str(envb.get(k, "")) != "1"]
                for k in added:
                    envb[k] = "1"
                if added:
                    p.add(path, "Claude Code", "env: " + ", ".join(f"{k}=1" for k in added), old,
                          json.dumps(data, indent=2) + "\n")
    if want("codex"):
        home_c = env.get("CODEX_HOME") or os.path.join(home, ".codex")
        if os.path.isdir(home_c):
            path = os.path.join(home_c, "config.toml")
            old = _read(path)
            new = toml_set(toml_set(old, "analytics", "enabled", "false"), "feedback", "enabled", "false")
            p.add(path, "Codex", "analytics.enabled = false, feedback.enabled = false", old, new)
    if want("gemini"):
        gdir = os.path.join(home, ".gemini")
        if os.path.isdir(gdir):
            path = os.path.join(gdir, "settings.json")
            old = _read(path)
            try:
                data = json.loads(old) if old.strip() else {}
            except ValueError:
                try:
                    json.loads(strip_jsonc(old))
                    p.skipped.append((path, 'has comments; add "privacy": {"usageStatisticsEnabled": false} by hand'))
                except ValueError:
                    p.skipped.append((path, "not valid JSON"))
                data = None
            if data is not None:
                data.setdefault("privacy", {})["usageStatisticsEnabled"] = False
                if "usageStatisticsEnabled" in data:
                    data["usageStatisticsEnabled"] = False
                p.add(path, "Gemini CLI", "privacy.usageStatisticsEnabled = false", old, json.dumps(data, indent=2) + "\n")
    if want("editors"):
        for app, label in EDITORS:
            base = app_config_dir(home, app, plat)
            if not os.path.isdir(base):
                continue
            path = os.path.join(base, "User", "settings.json")
            old = _read(path)
            try:
                new = jsonc_set_flat(old, "telemetry.telemetryLevel", "off")
                json.loads(strip_jsonc(new))
            except ValueError:
                p.skipped.append((path, "could not edit safely"))
                continue
            p.add(path, label, 'telemetry.telemetryLevel = "off"', old, new)
    if want("aider"):
        path = os.path.join(home, ".aider", "analytics.json")
        old = _read(path)
        if old.strip():
            try:
                data = json.loads(old)
            except ValueError:
                p.skipped.append((path, "not valid JSON"))
            else:
                if not data.get("permanently_disable"):
                    data["permanently_disable"] = True
                    data["asked_opt_in"] = True
                    p.add(path, "Aider", "permanently_disable = true", old, json.dumps(data, indent=4) + "\n")
    return p


def apply(p):
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backups = []
    for ch in p.changes:
        path = ch["path"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            b = f"{path}.optout-bak-{stamp}"
            shutil.copy2(path, b)
            backups.append(b)
        tmp = path + ".optout-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(ch["new"])
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    return backups
