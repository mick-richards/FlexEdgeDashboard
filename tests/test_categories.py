"""Tests for services.categories — category tree CRUD and leaf helpers."""
from __future__ import annotations

import json

from services.categories import (
    SEPARATOR,
    add_child,
    add_parent,
    child_of,
    leaves_of_parent,
    list_leaves,
    list_parents,
    load_tree,
    parent_of,
    remove_leaf,
    remove_parent,
    save_tree,
)


class TestLoadAndSave:
    def test_load_empty_when_no_file(self, categories_file):
        assert load_tree() == {}

    def test_roundtrip(self, categories_file, sample_tree):
        save_tree(sample_tree)
        assert load_tree() == sample_tree

    def test_save_creates_parent_dir(self, tmp_path, categories_file):
        # categories_file already patches; just ensure save doesn't crash
        save_tree({"Test": []})
        assert load_tree() == {"Test": []}


class TestListLeaves:
    def test_leaves_with_children(self, sample_categories_file):
        leaves = list_leaves()
        assert f"Salarissen{SEPARATOR}DGA salaris Mick" in leaves
        assert f"Salarissen{SEPARATOR}DGA salaris Joris" in leaves

    def test_childless_parent_is_leaf(self, sample_categories_file):
        leaves = list_leaves()
        assert "Kantoor" in leaves

    def test_leaves_order(self, sample_categories_file):
        leaves = list_leaves()
        # Salarissen children come before Kantoor (dict order)
        sal_idx = leaves.index(f"Salarissen{SEPARATOR}DGA salaris Mick")
        kantoor_idx = leaves.index("Kantoor")
        assert sal_idx < kantoor_idx

    def test_empty_tree(self, categories_file):
        assert list_leaves() == []

    def test_explicit_tree_arg(self, sample_tree):
        leaves = list_leaves(sample_tree)
        assert len(leaves) == 5  # 2 sal + 1 kantoor + 2 software


class TestListParents:
    def test_returns_parent_names(self, sample_categories_file):
        parents = list_parents()
        assert parents == ["Salarissen", "Kantoor", "Software & tools"]


class TestParentOf:
    def test_child_leaf(self):
        assert parent_of(f"Salarissen{SEPARATOR}DGA salaris Mick") == "Salarissen"

    def test_parent_leaf(self):
        assert parent_of("Kantoor") == "Kantoor"


class TestChildOf:
    def test_child_leaf(self):
        assert child_of(f"Salarissen{SEPARATOR}DGA salaris Mick") == "DGA salaris Mick"

    def test_parent_leaf(self):
        assert child_of("Kantoor") is None


class TestLeavesOfParent:
    def test_parent_with_children(self, sample_categories_file):
        leaves = leaves_of_parent("Salarissen")
        assert len(leaves) == 2
        assert all(l.startswith("Salarissen") for l in leaves)

    def test_childless_parent(self, sample_categories_file):
        assert leaves_of_parent("Kantoor") == ["Kantoor"]

    def test_unknown_parent(self, sample_categories_file):
        assert leaves_of_parent("Nonexistent") == []


class TestAddChild:
    def test_add_to_existing_parent(self, sample_categories_file):
        tree = add_child("Salarissen", "Stagevergoeding Tessa")
        assert "Stagevergoeding Tessa" in tree["Salarissen"]
        # Persisted
        assert "Stagevergoeding Tessa" in load_tree()["Salarissen"]

    def test_add_creates_parent_if_missing(self, sample_categories_file):
        tree = add_child("Nieuw", "Kind")
        assert tree["Nieuw"] == ["Kind"]

    def test_no_duplicate(self, sample_categories_file):
        add_child("Salarissen", "DGA salaris Mick")
        tree = load_tree()
        assert tree["Salarissen"].count("DGA salaris Mick") == 1

    def test_blank_input_noop(self, sample_categories_file):
        tree_before = load_tree()
        add_child("", "x")
        assert load_tree() == tree_before
        add_child("x", "  ")
        # "x" not added because child was blank after strip
        assert load_tree() == tree_before


class TestAddParent:
    def test_add_new_parent(self, sample_categories_file):
        tree = add_parent("Telecom")
        assert "Telecom" in tree
        assert tree["Telecom"] == []

    def test_existing_parent_noop(self, sample_categories_file):
        tree = add_parent("Kantoor")
        assert tree["Kantoor"] == []  # still empty


class TestRemoveLeaf:
    def test_remove_child(self, sample_categories_file):
        tree = remove_leaf(f"Salarissen{SEPARATOR}DGA salaris Mick")
        assert "DGA salaris Mick" not in tree["Salarissen"]
        assert "Salarissen" in tree  # parent stays

    def test_remove_childless_parent(self, sample_categories_file):
        tree = remove_leaf("Kantoor")
        assert "Kantoor" not in tree

    def test_remove_nonexistent_noop(self, sample_categories_file):
        tree_before = load_tree()
        tree = remove_leaf("Nonexistent")
        assert tree == tree_before


class TestRemoveParent:
    def test_remove_parent_with_children(self, sample_categories_file):
        tree = remove_parent("Salarissen")
        assert "Salarissen" not in tree

    def test_remove_nonexistent_noop(self, sample_categories_file):
        tree_before = load_tree()
        remove_parent("Nope")
        assert load_tree() == tree_before
