"""Shared fixtures for FlexEdge Dashboard tests.

Streamlit is stubbed out at import time so service modules load without
requiring a running Streamlit server or valid secrets.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# ── Stub streamlit before any service module is imported ──

_st_mock = MagicMock()
_st_mock.cache_data = lambda **kw: (lambda fn: fn)  # make @st.cache_data a no-op decorator
sys.modules.setdefault("streamlit", _st_mock)


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Return a temporary directory for tests that read/write JSON."""
    return tmp_path
