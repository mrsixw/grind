"""Shared fixtures for the unit tests."""

import pytest


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point XDG_STATE_HOME at a temporary directory for every test.

    The active working context lives in the state directory, and every CLI
    invocation reads it, so a test must never see, or overwrite, the real
    one. Tests that exercise the XDG lookup itself override this as needed.
    """
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    return state
