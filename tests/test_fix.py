import json
import os

import pytest

from optout import checks, fix
from optout.util import strip_jsonc


def scan(home):
    return {f["id"]: f for f in checks.scan(checks.Ctx(home=home, env={}, cwd=home, plat="linux"))}


def test_dry_run_changes_nothing(demo_home):
    before = open(os.path.join(demo_home, ".codex", "config.toml")).read()
    p = fix.plan(demo_home, env={})
    assert {c["tool"] for c in p.changes} == {"Claude Code", "Codex", "Gemini CLI", "VS Code", "Aider"}
    assert open(os.path.join(demo_home, ".codex", "config.toml")).read() == before


def test_write_fixes_every_local_warning(demo_home):
    p = fix.plan(demo_home, env={})
    backups = fix.apply(p)
    assert len(backups) == len(p.changes)
    f = scan(demo_home)
    for k in ("claude.telemetry", "claude.feedback", "claude.survey", "codex.analytics", "codex.feedback",
              "gemini.usage-stats", "code.telemetry", "aider.analytics"):
        assert f[k]["status"] == "ok", (k, f[k])
    # second plan is empty (idempotent)
    assert fix.plan(demo_home, env={}).changes == []


def test_keeps_existing_settings_and_comments(demo_home):
    fix.apply(fix.plan(demo_home, env={}))
    cc = json.load(open(os.path.join(demo_home, ".claude", "settings.json")))
    assert cc["permissions"]["allow"] == ["Bash(npm test)"] and cc["cleanupPeriodDays"] == 90
    assert cc["env"]["DISABLE_ERROR_REPORTING"] == "1"
    vs = open(os.path.join(demo_home, ".config", "Code", "User", "settings.json")).read()
    assert "// my editor" in vs and '"telemetry.telemetryLevel": "off"' in vs
    assert json.loads(strip_jsonc(vs))["editor.fontSize"] == 14
    toml = open(os.path.join(demo_home, ".codex", "config.toml")).read()
    assert "# Codex config" in toml and '[mcp_servers.docs]' in toml
    assert "[analytics]\nenabled = false" in toml


def test_toml_set_variants():
    assert fix.toml_set("", "analytics", "enabled", "false") == "[analytics]\nenabled = false\n"
    t = "analytics.enabled = true\n[x]\ny = 1\n"
    assert fix.toml_set(t, "analytics", "enabled", "false").startswith("analytics.enabled = false\n")
    t = "[analytics]\n  enabled = true\n[other]\nenabled = true\n"
    out = fix.toml_set(t, "analytics", "enabled", "false")
    assert "  enabled = false" in out and out.count("enabled = true") == 1
    t = "[analytics] # c\nfoo = 1\n"
    assert "[analytics] # c\nenabled = false\nfoo = 1" in fix.toml_set(t, "analytics", "enabled", "false")


def test_jsonc_set_flat_variants():
    assert json.loads(fix.jsonc_set_flat("", "k", "off")) == {"k": "off"}
    assert json.loads(fix.jsonc_set_flat("{}", "k", "off")) == {"k": "off"}
    assert json.loads(strip_jsonc(fix.jsonc_set_flat('{ "k": "all", // x\n "a": 1 }', "k", "off"))) == {"k": "off", "a": 1}
    assert json.loads(strip_jsonc(fix.jsonc_set_flat('{\n  // only a comment\n}', "k", "off"))) == {"k": "off"}


def test_invalid_claude_json_is_skipped(demo_home):
    with open(os.path.join(demo_home, ".claude", "settings.json"), "w") as fh:
        fh.write("{ // nope\n}")
    p = fix.plan(demo_home, env={}, only={"claude"})
    assert p.changes == [] and "strict JSON" in p.skipped[0][1]


def test_gemini_with_comments_is_skipped(demo_home):
    with open(os.path.join(demo_home, ".gemini", "settings.json"), "w") as fh:
        fh.write('{ // c\n "ui": {} }')
    p = fix.plan(demo_home, env={}, only={"gemini"})
    assert p.changes == [] and "by hand" in p.skipped[0][1]


def test_never_touches_cursor_db(demo_home):
    db = os.path.join(demo_home, ".config", "Cursor", "User", "globalStorage", "state.vscdb")
    before = open(db, "rb").read()
    fix.apply(fix.plan(demo_home, env={}))
    assert open(db, "rb").read() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_preserves_file_mode(demo_home):
    p = os.path.join(demo_home, ".codex", "config.toml")
    os.chmod(p, 0o600)
    fix.apply(fix.plan(demo_home, env={}, only={"codex"}))
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
