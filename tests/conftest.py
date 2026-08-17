import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Keep every test off the real plugin state directory."""
    import board

    state = tmp_path / "state"
    monkeypatch.setattr(board, "STATE_DIR", state)
    monkeypatch.setattr(board, "SESSIONS_PATH", state / "sessions.json")
    monkeypatch.setattr(board, "COMPANION_PATH", state / "companion.json")
