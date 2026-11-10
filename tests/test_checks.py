import json
import os
import sqlite3

import make_demo_home
from optout import accounts, checks


def by_id(findings):
    return {f["id"]: f for f in findings}


def scan(home, env=None, **kw):
    return by_id(checks.scan(checks.Ctx(home=home, env=env or {}, cwd=home, plat="linux", **kw)))


def test_empty_home_finds_nothing(tmp_path):
    assert checks.scan(checks.Ctx(home=str(tmp_path), env={}, cwd=str(tmp_path), plat="linux")) == []


def test_demo_home_statuses(demo_home):
    f = scan(demo_home)
    assert f["claude.telemetry"]["status"] == "warn"
    assert f["claude.error-reports"]["status"] == "ok"
    assert f["claude.transcripts"]["value"] == "90 days"
    assert f["claude.account-training"]["status"] == "unverified"
    assert "dev@example.com" in f["claude.account-training"]["detail"]
    assert f["codex.analytics"]["status"] == "warn"
    assert f["codex.feedback"]["status"] == "warn"
    assert f["chatgpt.account-training"]["tool"] == "Codex"
    assert f["gemini.usage-stats"]["status"] == "warn"
    assert f["gemini.telemetry"]["status"] == "warn"
    assert f["gemini.auth"]["status"] == "warn"
    assert f["code.telemetry"]["status"] == "warn"
    assert f["cursor.telemetry"]["status"] == "ok"
    assert f["cursor.privacy-mode"]["status"] == "ok"
    assert f["cursor.privacy-mode"]["strength"] == 2
    assert f["copilot.account-training"]["status"] == "unverified"
    assert f["aider.analytics"]["status"] == "warn"


def test_nonessential_traffic_covers_all_claude_flags(demo_home):
    f = scan(demo_home, env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
    for k in ("claude.telemetry", "claude.feedback", "claude.survey"):
        assert f[k]["status"] == "ok", k


def test_shell_env_overrides_settings(demo_home):
    f = scan(demo_home, env={"DISABLE_ERROR_REPORTING": "0"})
    assert f["claude.error-reports"]["status"] == "warn"


def test_do_not_track_disables_survey_only(demo_home):
    f = scan(demo_home, env={"DO_NOT_TRACK": "1"})
    assert f["claude.survey"]["status"] == "ok"
    assert f["claude.telemetry"]["status"] == "warn"


def test_bedrock_is_commercial_and_default_off(demo_home):
    f = scan(demo_home, env={"CLAUDE_CODE_USE_BEDROCK": "1"})
    assert f["claude.telemetry"]["status"] == "ok"
    assert f["claude.account-training"]["status"] == "ok"
    assert f["claude.account-training"]["value"] == "commercial terms"


def test_claude_otel_prompt_export(demo_home):
    f = scan(demo_home, env={"CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_LOG_USER_PROMPTS": "1",
                             "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example"})
    assert f["claude.otel"]["status"] == "warn"
    assert "otel.example" in f["claude.otel"]["value"]


def test_claude_managed_settings(demo_home, monkeypatch, tmp_path):
    m = tmp_path / "managed-settings.json"
    m.write_text(json.dumps({"env": {"DISABLE_TELEMETRY": "1"}}))
    monkeypatch.setattr(checks, "claude_managed_paths", lambda plat: [str(m)])
    f = scan(demo_home)
    assert f["claude.telemetry"]["status"] == "ok"
    assert "(managed)" in f["claude.telemetry"]["source"]


def test_codex_api_key_mode(demo_home):
    p = os.path.join(demo_home, ".codex", "auth.json")
    with open(p, "w") as fh:
        json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-test"}, fh)
    f = scan(demo_home)
    assert f["codex.account-training"]["status"] == "ok"
    assert "sk-test" not in json.dumps(list(f.values()))


def test_codex_otel_prompts_and_codex_home(demo_home, tmp_path):
    ch = tmp_path / "codexhome"
    ch.mkdir()
    (ch / "config.toml").write_text('[analytics]\nenabled = false\n[feedback]\nenabled = false\n'
                                    '[otel]\nlog_user_prompt = true\nexporter = "otlp-http"\n')
    f = scan(demo_home, env={"CODEX_HOME": str(ch)})
    assert f["codex.analytics"]["status"] == "ok"
    assert f["codex.feedback"]["status"] == "ok"
    assert f["codex.otel-prompts"]["status"] == "warn"


def test_gemini_opted_out_and_prompts_off(demo_home):
    proj = os.path.join(demo_home, ".gemini", "settings.json")
    with open(proj, "w") as fh:
        json.dump({"privacy": {"usageStatisticsEnabled": False}, "telemetry": {"enabled": True, "logPrompts": False}}, fh)
    f = scan(demo_home)
    assert f["gemini.usage-stats"]["status"] == "ok"
    assert f["gemini.telemetry"]["status"] == "info"


def test_gemini_legacy_top_level_key(demo_home):
    with open(os.path.join(demo_home, ".gemini", "settings.json"), "w") as fh:
        json.dump({"usageStatisticsEnabled": False}, fh)
    assert scan(demo_home)["gemini.usage-stats"]["status"] == "ok"


def _cursor_mode(home, mode=None, legacy=None, share=None):
    db = os.path.join(home, ".config", "Cursor", "User", "globalStorage", "state.vscdb")
    con = sqlite3.connect(db)
    con.execute("DELETE FROM ItemTable")
    if mode:
        con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorai/donotchange/newPrivacyMode2", json.dumps({"privacyMode": mode})))
    if legacy is not None:
        con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorai/donotchange/privacyMode", legacy))
    if share is not None:
        con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorai/donotchange/partnerDataShare", share))
    con.commit()
    con.close()


def test_cursor_training_allowed_is_bad(demo_home):
    _cursor_mode(demo_home, "PRIVACY_MODE_USAGE_CODEBASE_TRAINING_ALLOWED", share="true")
    f = scan(demo_home)
    assert f["cursor.privacy-mode"]["status"] == "bad"
    assert f["cursor.partner-share"]["status"] == "bad"
    assert checks.worst(list(f.values())) == 3


def test_cursor_no_training_and_legacy_and_missing(demo_home):
    _cursor_mode(demo_home, "PRIVACY_MODE_NO_TRAINING")
    f = scan(demo_home)["cursor.privacy-mode"]
    assert f["status"] == "ok" and f["strength"] == 1
    _cursor_mode(demo_home, legacy="false")
    assert scan(demo_home)["cursor.privacy-mode"]["status"] == "bad"
    _cursor_mode(demo_home)
    assert scan(demo_home)["cursor.privacy-mode"]["status"] == "unknown"


def test_cursor_db_bytes_value(demo_home):
    db = os.path.join(demo_home, ".config", "Cursor", "User", "globalStorage", "state.vscdb")
    con = sqlite3.connect(db)
    con.execute("DELETE FROM ItemTable")
    con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorai/donotchange/newPrivacyMode2",
                                                         json.dumps({"privacyMode": "PRIVACY_MODE_NO_TRAINING"}).encode()))
    con.commit()
    con.close()
    assert scan(demo_home)["cursor.privacy-mode"]["status"] == "ok"


def test_attestation_flow(demo_home):
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    accounts.record("claude", "off", home=demo_home, when=now - dt.timedelta(days=3))
    accounts.record("copilot", "off", home=demo_home, when=now - dt.timedelta(days=40))
    accounts.record("mistral", "on", home=demo_home)
    f = scan(demo_home)
    assert f["claude.account-training"]["status"] == "ok"
    assert f["copilot.account-training"]["status"] == "stale"
    assert f["mistral.account-training"]["status"] == "bad"
    assert f["mistral.account-training"]["tool"] == "Mistral Le Chat"
    f = scan(demo_home, max_age=60)
    assert f["copilot.account-training"]["status"] == "ok"


def test_macos_paths(tmp_path):
    home = str(tmp_path)
    p = os.path.join(home, "Library", "Application Support", "Code", "User")
    os.makedirs(p)
    with open(os.path.join(p, "settings.json"), "w") as fh:
        fh.write('{"telemetry.telemetryLevel": "crash"}')
    f = by_id(checks.scan(checks.Ctx(home=home, env={}, cwd=home, plat="mac")))
    assert f["code.telemetry"]["status"] == "info"
    assert f["code.telemetry"]["value"] == "crash"


def test_only_filter(demo_home):
    f = checks.scan(checks.Ctx(home=demo_home, env={}, cwd=demo_home, plat="linux"), only={"codex"})
    assert {x["tool"] for x in f} == {"Codex"}


def test_aider_never_opted_in(demo_home):
    with open(os.path.join(demo_home, ".aider", "analytics.json"), "w") as fh:
        json.dump({"uuid": "x", "asked_opt_in": False}, fh)
    assert scan(demo_home)["aider.analytics"]["status"] == "ok"
