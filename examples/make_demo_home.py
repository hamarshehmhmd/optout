"""Build a fake home directory with typical AI-tool configs (no real accounts or secrets).

Usage: python examples/make_demo_home.py /tmp/demo-home
"""
import json
import os
import shutil
import sqlite3
import sys


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def cursor_db(home, mode="PRIVACY_MODE_NO_STORAGE"):
    db = os.path.join(home, ".config", "Cursor", "User", "globalStorage", "state.vscdb")
    os.makedirs(os.path.dirname(db), exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorai/donotchange/privacyMode", "true"))
    con.execute("INSERT INTO ItemTable VALUES (?, ?)",
                ("cursorai/donotchange/newPrivacyMode2", json.dumps({"privacyMode": mode})))
    con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorai/donotchange/partnerDataShare", "false"))
    con.commit()
    con.close()
    return db


def main(home):
    if os.path.exists(home):
        shutil.rmtree(home)
    w(os.path.join(home, ".claude", "settings.json"), json.dumps({
        "permissions": {"allow": ["Bash(npm test)"]},
        "cleanupPeriodDays": 90,
        "env": {"DISABLE_ERROR_REPORTING": "1"},
    }, indent=2) + "\n")
    w(os.path.join(home, ".claude.json"), json.dumps({
        "oauthAccount": {"emailAddress": "dev@example.com"}, "numStartups": 12}, indent=2))
    w(os.path.join(home, ".codex", "config.toml"),
      '# Codex config\nmodel = "gpt-5.5-codex"\napproval_policy = "on-request"\n\n'
      '[history]\npersistence = "save-all"\n\n[mcp_servers.docs]\ncommand = "npx"\nargs = ["-y", "docs-mcp"]\n')
    w(os.path.join(home, ".codex", "auth.json"), json.dumps({"auth_mode": "chatgpt", "tokens": {"id_token": "redacted"}}))
    w(os.path.join(home, ".gemini", "settings.json"), json.dumps({
        "security": {"auth": {"selectedType": "gemini-api-key"}},
        "telemetry": {"enabled": True, "target": "gcp"},
        "ui": {"theme": "GitHub"},
    }, indent=2) + "\n")
    w(os.path.join(home, ".config", "Code", "User", "settings.json"),
      '{\n    // my editor\n    "editor.fontSize": 14,\n    "files.autoSave": "afterDelay",\n}\n')
    os.makedirs(os.path.join(home, ".vscode", "extensions", "github.copilot-chat-0.31.2"), exist_ok=True)
    w(os.path.join(home, ".config", "Cursor", "User", "settings.json"), '{\n  "telemetry.telemetryLevel": "off"\n}\n')
    cursor_db(home)
    w(os.path.join(home, ".aider", "analytics.json"),
      json.dumps({"uuid": "0f8b7c1e-demo", "permanently_disable": False, "asked_opt_in": True}))
    print(f"demo home ready: {home}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo-home")
