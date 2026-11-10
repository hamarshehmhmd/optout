import json
import os
import subprocess
import sys

import pytest

from optout import checks, cli, util


@pytest.fixture(autouse=True)
def _linux_layout(monkeypatch):
    # demo homes use the Linux layout (~/.config/Code/...) on every OS
    monkeypatch.setattr(checks, "platform_name", lambda: "linux")
    monkeypatch.setattr(util, "platform_name", lambda: "linux")


def run(capsys, *args):
    rc = cli.main(["--color", "never", *args])
    return rc, capsys.readouterr().out


def test_scan_table_and_exit_codes(demo_home, capsys):
    rc, out = run(capsys, "--home", demo_home, "scan")
    assert rc == 0 and "Claude Code" in out and "WARN" in out and "TODO" in out
    rc, _ = run(capsys, "--home", demo_home, "scan", "--fail-on", "warn")
    assert rc == 1
    rc, _ = run(capsys, "--home", demo_home, "scan", "--fail-on", "never")
    assert rc == 0


def test_default_command_is_scan(demo_home, capsys):
    rc, out = run(capsys, "--home", demo_home)
    assert "Codex" in out


def test_scan_json_and_md(demo_home, capsys):
    rc, out = run(capsys, "--home", demo_home, "scan", "--format", "json")
    d = json.loads(out)
    assert d["version"] and any(f["id"] == "cursor.privacy-mode" for f in d["findings"])
    rc, out = run(capsys, "--home", demo_home, "scan", "--format", "md")
    assert out.startswith("| Tool |")


def test_fix_dry_run_then_write(demo_home, capsys):
    rc, out = run(capsys, "--home", demo_home, "fix")
    assert "would set" in out and "Dry run" in out
    rc, out = run(capsys, "--home", demo_home, "fix", "--write")
    assert "Wrote 5 file(s)" in out
    rc, out = run(capsys, "--home", demo_home, "fix")
    assert "Nothing to change" in out


def test_attest_accounts_open(demo_home, capsys):
    rc, out = run(capsys, "--home", demo_home, "attest", "claude", "off", "--note", "checked")
    assert rc == 0 and "recorded claude: off" in out
    rc, out = run(capsys, "--home", demo_home, "accounts")
    assert "OK" in out and "claude" in out and "TODO" in out
    rc, out = run(capsys, "--home", demo_home, "accounts", "--format", "json")
    assert json.loads(out)["claude"]["status"] == "ok"
    rc, out = run(capsys, "--home", demo_home, "open", "chatgpt", "--print-only")
    assert "chatgpt.com/#settings/DataControls" in out
    rc = cli.main(["--home", demo_home, "attest", "nope", "off"])
    assert rc == 2


def test_baseline_drift_cli(demo_home, capsys):
    import make_demo_home
    rc, _ = run(capsys, "--home", demo_home, "drift")
    assert rc == 2
    run(capsys, "--home", demo_home, "baseline")
    rc, out = run(capsys, "--home", demo_home, "drift")
    assert rc == 0 and "no drift" in out
    make_demo_home.cursor_db(demo_home, "PRIVACY_MODE_NO_TRAINING")
    rc, out = run(capsys, "--home", demo_home, "drift")
    assert rc == 3 and "WEAKER" in out and "Privacy Mode" in out
    rc, out = run(capsys, "--home", demo_home, "drift", "--format", "json")
    assert rc == 3 and json.loads(out)["changes"][0]["kind"] == "weaker"


def test_terms_cli_with_pages_file(tmp_path, capsys):
    page = tmp_path / "p.html"
    page.write_text("<html><body><main>" + "<p>We may use your content to improve models. %d</p>" * 10 % tuple(range(10)) + "</main></body></html>")
    pf = tmp_path / "pages.json"
    pf.write_text(json.dumps({"pages": [{"id": "demo", "vendor": "Demo", "url": page.as_uri()}]}))
    home = str(tmp_path / "h")
    rc, out = run(capsys, "--home", home, "terms", "--pages", str(pf))
    assert rc == 0 and "NEW" in out
    page.write_text(page.read_text().replace("may use", "will use"))
    rc, out = run(capsys, "--home", home, "terms", "--pages", str(pf), "--diff")
    assert rc == 3 and "CHANGED" in out and "+We will use" in out


def test_module_entrypoint(demo_home):
    env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
    p = subprocess.run([sys.executable, "-m", "optout", "--version"], capture_output=True, text=True, env=env)
    assert p.returncode == 0 and p.stdout.startswith("optout ")


def test_no_tools_message(tmp_path, capsys):
    rc, out = run(capsys, "--home", str(tmp_path), "scan")
    assert rc == 0 and "No supported AI tools found" in out
