"""
Central loader + enforcer for the expected columns of each category,
sourced from monitor/websites-config.yml (the `_col_<category>_listing`
anchors).

Used by:
  - Simple_Category/main.py
  - Sub_and_Sub_Sub_Categories/main.py
  - Users/user_scraper.py
  - Jobs/jobs_scraper.py
  - Cars_for_sale/main.py

Public API:
  - load_all_expected_columns()  -> dict[category, list[column]]
  - enforce_columns(df, expected) -> reordered df with missing cols as None
  - enforce_for_category(df, category) -> convenience wrapper
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Iterable

import pandas as pd


# Common_files/columns_loader.py  →  parents[0]=Common_files, parents[1]=QatarSale
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "monitor" / "websites-config.yml"

# categories whose name in the workflow differs from the key in the config
CATEGORY_ALIASES: dict[str, str] = {
    "car_spare_parts_accessories-automotive_exterior_accessories":
        "car_spare_parts_accessories",
}


def _extract_columns(raw: object) -> list[str] | None:
    """
    The anchor `&col_X_listing` is normally a YAML list of strings.
    Some authors wrap it inside a dict (e.g. `columns: [...]`),
    so this normalizes whatever we find to a plain list of strings.
    """
    if isinstance(raw, list):
        return [str(c) for c in raw]
    if isinstance(raw, dict):
        for key in ("columns", "cols", "fields", "fields_list", "list"):
            if key in raw and isinstance(raw[key], list):
                return [str(c) for c in raw[key]]
    return None


def load_all_expected_columns() -> dict[str, list[str]]:
    """
    Returns {category: [col, col, ...]} by reading every top-level key of the
    form `_col_<category>_listing` in websites-config.yml.
    """
    if not _CONFIG_PATH.exists():
        print(f"⚠️ [columns_loader] {_CONFIG_PATH} not found -- column enforcement disabled.")
        return {}

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"⚠️ [columns_loader] Failed to parse {_CONFIG_PATH}: {e}")
        return {}

    if not isinstance(cfg, dict):
        print(f"⚠️ [columns_loader] {_CONFIG_PATH} did not parse into a dict -- enforcement disabled.")
        return {}

    result: dict[str, list[str]] = {}
    for key, value in cfg.items():
        if not isinstance(key, str):
            continue
        if not (key.startswith("_col_") and key.endswith("_listing")):
            continue
        category = key[len("_col_"):-len("_listing")]
        cols = _extract_columns(value)
        if cols:
            result[category] = cols

    return result


def enforce_columns(df: pd.DataFrame, expected: Iterable[str]) -> pd.DataFrame:
    """
    - Adds any missing expected column with None.
    - Expands the `specs_*` wildcard: keeps every `specs_*` column found in
      the df (sorted); if none exist, adds a placeholder column literally
      named `specs_*` so the schema stays explicit.
    - Reorders columns: expected first (in YAML order), then any leftover
      columns not in the config (appended at the end).
    """
    expected = list(expected)
    if not expected:
        return df

    df = df.copy()

    has_specs_wildcard = "specs_*" in expected
    expected_fixed = [c for c in expected if c != "specs_*"]

    # 1) add missing fixed columns
    for col in expected_fixed:
        if col not in df.columns:
            df[col] = None

    # 2) handle specs_* wildcard
    if has_specs_wildcard:
        existing_specs = sorted(c for c in df.columns if c.startswith("specs_"))
        if not existing_specs:
            df["specs_*"] = None
            existing_specs = ["specs_*"]
    else:
        existing_specs = []

    # 3) build final column order
    ordered: list[str] = []
    for col in expected:
        if col == "specs_*":
            ordered.extend(existing_specs)
        elif col in df.columns:
            ordered.append(col)

    leftovers = [c for c in df.columns if c not in ordered]
    final_cols = ordered + leftovers

    # dedupe while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for c in final_cols:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    return df[deduped]


def enforce_for_category(
    df: pd.DataFrame,
    category: str,
    *,
    expected_columns: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """
    Convenience wrapper. If `expected_columns` is None, it reloads the config
    (cheap). Most callers should load once and pass it in.
    """
    if expected_columns is None:
        expected_columns = load_all_expected_columns()

    key = CATEGORY_ALIASES.get(category, category)
    expected = expected_columns.get(key)

    if not expected:
        return df

    return enforce_columns(df, expected)