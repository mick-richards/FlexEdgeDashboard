"""Shared fixtures for FlexEdgeDashboard tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory and patch file paths in services."""
    return tmp_path


@pytest.fixture
def categories_file(tmp_data_dir):
    """Patch categories.CATEGORIES_FILE to a temp location."""
    fp = tmp_data_dir / "categories.json"
    with patch("services.categories.CATEGORIES_FILE", fp):
        yield fp


@pytest.fixture
def cost_plan_file(tmp_data_dir):
    """Patch cost_plan.COST_FILE to a temp location."""
    fp = tmp_data_dir / "cost_plan.json"
    with patch("services.cost_plan.COST_FILE", fp):
        yield fp


@pytest.fixture
def overrides_file(tmp_data_dir):
    """Patch actuals.OVERRIDES_FILE to a temp location."""
    fp = tmp_data_dir / "category_overrides.json"
    with patch("services.actuals.OVERRIDES_FILE", fp):
        yield fp


@pytest.fixture
def sample_tree():
    return {
        "Salarissen": ["DGA salaris Mick", "DGA salaris Joris"],
        "Kantoor": [],
        "Software & tools": ["GitHub", "Streamlit"],
    }


@pytest.fixture
def sample_categories_file(categories_file, sample_tree):
    """Write a sample tree to the temp categories file."""
    categories_file.write_text(
        json.dumps({"schema_version": 1, "tree": sample_tree}), encoding="utf-8"
    )
    return categories_file
