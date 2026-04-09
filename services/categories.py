"""Centralised category tree — single source of truth for Uitgaven and Kostenplan.

Structure in `data/categories.json`:

    {
      "schema_version": 1,
      "tree": {
        "Salarissen": ["DGA salaris Mick", "DGA salaris Joris", ...],
        "Kantoor": [],
        ...
      }
    }

Terminology used throughout the codebase:
    - "parent"  → a top-level key in `tree`
    - "child"   → a member of a parent's list
    - "leaf"    → something that can receive money: either a parent with no children,
                  or any child. Leaves are identified by a full-path string:
                      "Salarissen/DGA salaris Mick"   (parent has children → leaf = child)
                      "Kantoor"                        (parent has no children → leaf = parent)
    - "full name" = the leaf string above (used as key in cost plans, expense overrides, etc.)
"""
from __future__ import annotations

import json
from pathlib import Path

CATEGORIES_FILE = Path(__file__).parent.parent / "data" / "categories.json"
SEPARATOR = " / "


def load_tree() -> dict[str, list[str]]:
    """Return the category tree: {parent: [child, child, ...]}. Empty list = parent is itself a leaf."""
    if not CATEGORIES_FILE.exists():
        return {}
    data = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
    return dict(data.get("tree", {}))


def save_tree(tree: dict[str, list[str]]) -> None:
    CATEGORIES_FILE.parent.mkdir(exist_ok=True)
    payload = {"schema_version": 1, "tree": tree}
    CATEGORIES_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def list_leaves(tree: dict[str, list[str]] | None = None) -> list[str]:
    """Return all leaf full-names in display order."""
    tree = tree if tree is not None else load_tree()
    leaves: list[str] = []
    for parent, children in tree.items():
        if children:
            for child in children:
                leaves.append(f"{parent}{SEPARATOR}{child}")
        else:
            leaves.append(parent)
    return leaves


def list_parents(tree: dict[str, list[str]] | None = None) -> list[str]:
    """Return the list of parent categories (for grouped rollups)."""
    tree = tree if tree is not None else load_tree()
    return list(tree.keys())


def parent_of(leaf: str, tree: dict[str, list[str]] | None = None) -> str:
    """Given a leaf full-name, return its parent category (for aggregation)."""
    if SEPARATOR in leaf:
        return leaf.split(SEPARATOR, 1)[0]
    return leaf


def child_of(leaf: str) -> str | None:
    """Given a leaf full-name, return the child part (or None if the leaf is a parent)."""
    if SEPARATOR in leaf:
        return leaf.split(SEPARATOR, 1)[1]
    return None


def leaves_of_parent(parent: str, tree: dict[str, list[str]] | None = None) -> list[str]:
    """Return the leaf full-names that belong to a given parent."""
    tree = tree if tree is not None else load_tree()
    children = tree.get(parent, [])
    if children:
        return [f"{parent}{SEPARATOR}{c}" for c in children]
    if parent in tree:
        return [parent]
    return []


def add_child(parent: str, child: str) -> dict[str, list[str]]:
    """Add a child to an existing parent (creates the parent if missing). Returns the updated tree."""
    parent = parent.strip()
    child = child.strip()
    if not parent or not child:
        return load_tree()
    tree = load_tree()
    if parent not in tree:
        tree[parent] = []
    if child not in tree[parent]:
        tree[parent].append(child)
    save_tree(tree)
    return tree


def add_parent(parent: str) -> dict[str, list[str]]:
    parent = parent.strip()
    if not parent:
        return load_tree()
    tree = load_tree()
    if parent not in tree:
        tree[parent] = []
        save_tree(tree)
    return tree


def remove_leaf(full_name: str) -> dict[str, list[str]]:
    """Remove a leaf. If the leaf is the last child of a parent, the parent is kept (as a leaf itself)."""
    tree = load_tree()
    if SEPARATOR in full_name:
        parent, child = full_name.split(SEPARATOR, 1)
        if parent in tree and child in tree[parent]:
            tree[parent].remove(child)
            save_tree(tree)
    else:
        # Removing a parent-leaf (one without children): drop the entire parent.
        if full_name in tree and not tree[full_name]:
            del tree[full_name]
            save_tree(tree)
    return tree


def remove_parent(parent: str) -> dict[str, list[str]]:
    """Remove a whole parent (including all its children)."""
    tree = load_tree()
    if parent in tree:
        del tree[parent]
        save_tree(tree)
    return tree
