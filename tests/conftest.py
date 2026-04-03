"""Shared fixtures for FlexEdge Dashboard tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect DATA_DIR to a temporary directory for isolated file I/O tests."""
    monkeypatch.setattr("services.emissions.DATA_DIR", tmp_path)
    monkeypatch.setattr("services.travel.DATA_DIR", tmp_path)
    return tmp_path
