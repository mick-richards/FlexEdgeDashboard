"""Cost plan service — month-keyed storage with rolling window, history and actuals.

Data file: `data/cost_plan.json`

    {
      "schema_version": 2,
      "months": {
        "2026-01": {
          "recurring": {"Salarissen / DGA salaris Mick": 2500, "Kantoor": 500, ...},
          "actuals":   {"Salarissen / DGA salaris Mick": 2500, "Kantoor": 487.30, ...},
          "one_offs":  [{"description": "...", "amount": 1234}, ...],
          "closed":    true
        },
        "2026-02": { ... },
        ...
      }
    }

Semantics:
    - `months` is the authoritative store — every month since 2026-01 lives here.
    - `recurring` holds the BEGROTE (planned) values per leaf category.
    - `actuals` holds the WERKELIJKE values per leaf category — only populated once a
      month is closed (either manually or automatically when the month has passed).
    - `closed = true` means the month is retrospective: the editor should lock the
      recurring values so historical budgets stay intact for variance analysis.
    - One-offs stay per-month.

The module also provides a legacy-compat helper `legacy_year_view(year)` that emits
the old `{"categories": {name: [12 values]}, "one_offs": [...]}` shape so the existing
consumer pages (Weekstart, Maandreview, Runway, Omzet) keep working without a rewrite.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from services import categories as cat_mod

COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
HISTORY_START = "2026-01"  # earliest month the plan keeps as history

# Default values used when we bootstrap the very first plan (no file yet).
# These are the values we carry forward via ensure_month() if nothing else exists.
_DEFAULT_RECURRING: dict[str, float] = {
    "Salarissen / DGA salaris Mick": 3625.0,
    "Salarissen / DGA salaris Joris": 2000.0,
    "Salarissen / Stagevergoeding Tessa": 500.0,
    "Kantoor": 800.0,
    "Software & tools": 300.0,
    "Boekhouder": 200.0,
    "Verzekeringen": 200.0,
    "Kantoorartikelen": 50.0,
    "Capital Goods": 0.0,
    "Reiskosten": 300.0,
    "Overig": 200.0,
}

MONTH_NAMES_NL = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]


# ─── core I/O ────────────────────────────────────────────────────────────────

def load_plan() -> dict:
    if COST_FILE.exists():
        data = json.loads(COST_FILE.read_text(encoding="utf-8"))
        if "months" not in data:
            # Migrate legacy shape {"categories": {name: [12 vals]}, "one_offs": [...]}
            return _migrate_legacy(data)
        return data
    return {"schema_version": 2, "months": {}}


def save_plan(plan: dict) -> None:
    COST_FILE.parent.mkdir(exist_ok=True)
    plan["schema_version"] = 2
    COST_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


def _migrate_legacy(legacy: dict) -> dict:
    """Convert old `{categories: {name: [12]}, one_offs: [{month,...}]}` to new shape (assumed 2026)."""
    year = 2026
    months: dict[str, dict] = {}
    categories = legacy.get("categories", {})
    one_offs = legacy.get("one_offs", [])
    for m_idx in range(12):
        ym = f"{year}-{m_idx + 1:02d}"
        months[ym] = {
            "recurring": {name: float(vals[m_idx]) for name, vals in categories.items()},
            "actuals": {},
            "one_offs": [
                {"description": oo.get("description", ""), "amount": float(oo.get("amount", 0))}
                for oo in one_offs
                if oo.get("month") == m_idx
            ],
            "closed": False,
        }
    return {"schema_version": 2, "months": months}


# ─── month keys and windows ──────────────────────────────────────────────────

def current_ym(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year}-{today.month:02d}"


def ym_add(ym: str, delta_months: int) -> str:
    y, m = map(int, ym.split("-"))
    total = y * 12 + (m - 1) + delta_months
    return f"{total // 12}-{(total % 12) + 1:02d}"


def ym_to_label(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{MONTH_NAMES_NL[m - 1]} {y}"


def rolling_months(n: int = 12, today: date | None = None) -> list[str]:
    """Return the next `n` month keys starting at the current month."""
    start = current_ym(today)
    return [ym_add(start, i) for i in range(n)]


def history_months(today: date | None = None, start: str = HISTORY_START) -> list[str]:
    """Return the list of past month keys, from HISTORY_START up to (but excluding) the current month."""
    cur = current_ym(today)
    months: list[str] = []
    ym = start
    while ym < cur:
        months.append(ym)
        ym = ym_add(ym, 1)
    return months


# ─── month access helpers ────────────────────────────────────────────────────

def ensure_month(plan: dict, ym: str) -> dict:
    """Make sure a month entry exists. Seeds recurring values from the previous month
    (or from _DEFAULT_RECURRING if no previous month exists). Returns the month dict."""
    months = plan.setdefault("months", {})
    if ym in months:
        return months[ym]

    # Seed recurring from previous month, else defaults.
    prev_ym = ym_add(ym, -1)
    if prev_ym in months:
        recurring = deepcopy(months[prev_ym].get("recurring", {}))
    else:
        recurring = deepcopy(_DEFAULT_RECURRING)

    months[ym] = {
        "recurring": recurring,
        "actuals": {},
        "one_offs": [],
        "closed": False,
    }
    return months[ym]


def get_recurring(plan: dict, ym: str) -> dict[str, float]:
    return dict(plan.get("months", {}).get(ym, {}).get("recurring", {}))


def set_recurring_cell(plan: dict, ym: str, leaf: str, value: float) -> None:
    month = ensure_month(plan, ym)
    month["recurring"][leaf] = float(value)


def get_actuals(plan: dict, ym: str) -> dict[str, float]:
    return dict(plan.get("months", {}).get(ym, {}).get("actuals", {}))


def set_actuals(plan: dict, ym: str, actuals: dict[str, float]) -> None:
    month = ensure_month(plan, ym)
    month["actuals"] = {k: float(v) for k, v in actuals.items()}


def get_one_offs(plan: dict, ym: str) -> list[dict]:
    return list(plan.get("months", {}).get(ym, {}).get("one_offs", []))


def add_one_off(plan: dict, ym: str, description: str, amount: float) -> None:
    month = ensure_month(plan, ym)
    month["one_offs"].append({"description": description, "amount": float(amount)})


def remove_one_off(plan: dict, ym: str, index: int) -> None:
    month = plan.get("months", {}).get(ym)
    if month and 0 <= index < len(month.get("one_offs", [])):
        month["one_offs"].pop(index)


# ─── close / variance ────────────────────────────────────────────────────────

def is_closed(plan: dict, ym: str) -> bool:
    return bool(plan.get("months", {}).get(ym, {}).get("closed", False))


def mark_closed(plan: dict, ym: str, closed: bool = True) -> None:
    month = ensure_month(plan, ym)
    month["closed"] = bool(closed)


def month_total_recurring(plan: dict, ym: str) -> float:
    return sum(float(v) for v in get_recurring(plan, ym).values())


def month_total_oneoff(plan: dict, ym: str) -> float:
    return sum(float(oo.get("amount", 0)) for oo in get_one_offs(plan, ym))


def month_total_actual(plan: dict, ym: str) -> float:
    return sum(float(v) for v in get_actuals(plan, ym).values())


def month_total(plan: dict, ym: str) -> float:
    """Planned total = recurring + one-offs (BEGROOT)."""
    return month_total_recurring(plan, ym) + month_total_oneoff(plan, ym)


# ─── category management (shared with categories service) ───────────────────

def all_used_leaves(plan: dict) -> set[str]:
    """Return every leaf name that currently appears in any month (recurring or actuals)."""
    used: set[str] = set()
    for m in plan.get("months", {}).values():
        used.update(m.get("recurring", {}).keys())
        used.update(m.get("actuals", {}).keys())
    return used


def drop_category_everywhere(plan: dict, leaf: str) -> None:
    """Remove a leaf from every month so it truly disappears from the plan."""
    for m in plan.get("months", {}).values():
        m.get("recurring", {}).pop(leaf, None)
        m.get("actuals", {}).pop(leaf, None)


def rename_category_everywhere(plan: dict, old: str, new: str) -> None:
    for m in plan.get("months", {}).values():
        rec = m.get("recurring", {})
        if old in rec:
            rec[new] = rec.pop(old)
        act = m.get("actuals", {})
        if old in act:
            act[new] = act.pop(old)


# ─── legacy compat for other consumer pages ──────────────────────────────────

def legacy_year_view(year: int, plan: dict | None = None) -> dict:
    """Return a dict in the OLD shape so the existing Weekstart/Maandreview/Runway/Omzet
    pages keep working without modification.

        {
          "categories": {"Salarissen / DGA salaris Mick": [12 monthly values], ...},
          "one_offs":   [{"month": 0-11, "description": "...", "amount": 1234}, ...]
        }

    Each monthly value is the *actuals* if the month is closed and has actuals,
    otherwise the *recurring* (planned) value. This means consumer dashboards will
    automatically reflect real spend for past months and forecast for the future —
    exactly the behaviour requested for the actuals flow.
    """
    plan = plan if plan is not None else load_plan()
    months = plan.get("months", {})

    # Union of leaves used across the 12 months in scope
    leaves: set[str] = set()
    month_entries: list[tuple[int, str, dict]] = []
    for m_idx in range(12):
        ym = f"{year}-{m_idx + 1:02d}"
        m = months.get(ym, {})
        month_entries.append((m_idx, ym, m))
        leaves.update(m.get("recurring", {}).keys())

    categories: dict[str, list[float]] = {leaf: [0.0] * 12 for leaf in sorted(leaves)}
    one_offs: list[dict] = []

    for m_idx, ym, m in month_entries:
        closed = bool(m.get("closed", False))
        actuals = m.get("actuals", {})
        recurring = m.get("recurring", {})
        for leaf in leaves:
            if closed and actuals:
                val = float(actuals.get(leaf, recurring.get(leaf, 0.0)))
            else:
                val = float(recurring.get(leaf, 0.0))
            categories[leaf][m_idx] = val
        for oo in m.get("one_offs", []):
            one_offs.append({
                "month": m_idx,
                "description": oo.get("description", ""),
                "amount": float(oo.get("amount", 0)),
            })

    return {"categories": categories, "one_offs": one_offs}


# ─── auto-close policy ───────────────────────────────────────────────────────

def auto_close_past_months(plan: dict, today: date | None = None) -> list[str]:
    """Mark every month strictly before the current month as closed. Returns the list of newly-closed keys."""
    cur = current_ym(today)
    newly: list[str] = []
    for ym, m in plan.get("months", {}).items():
        if ym < cur and not m.get("closed"):
            m["closed"] = True
            newly.append(ym)
    return newly
