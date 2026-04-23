"""Shared fixtures for FlexEdge Dashboard tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Stub out streamlit before any service import ──
# Services use st.secrets and st.cache_data at import time, so we need
# a lightweight fake that won't require a running Streamlit server.

_secrets_mock = MagicMock()
_secrets_mock.get = MagicMock(side_effect=lambda key, default="": default)

_st_mock = MagicMock()
_st_mock.secrets = _secrets_mock
# cache_data should act as a transparent decorator
_st_mock.cache_data = lambda **kwargs: (lambda fn: fn)
_st_mock.session_state = {}

sys.modules.setdefault("streamlit", _st_mock)


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect DATA_DIR in emissions and travel modules to a temp directory."""
    import services.emissions as emi
    import services.travel as trv

    monkeypatch.setattr(emi, "DATA_DIR", tmp_path)
    monkeypatch.setattr(trv, "DATA_DIR", tmp_path)
    return tmp_path
