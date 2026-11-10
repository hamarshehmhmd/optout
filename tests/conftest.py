import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "examples"))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith(("DISABLE_", "CLAUDE_", "DO_NOT_TRACK", "OTEL_", "GEMINI_", "CODEX_HOME", "ANTHROPIC_", "OPTOUT_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")


@pytest.fixture
def demo_home(tmp_path):
    import make_demo_home
    home = str(tmp_path / "home")
    make_demo_home.main(home)
    return home
