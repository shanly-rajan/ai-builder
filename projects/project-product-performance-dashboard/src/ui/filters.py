"""Scope-safe sidebar filters and relational filtering helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from src.ui.components import sidebar_scope_note


@dataclass(frozen=True)
class FilterResult:
    frame: pd.DataFrame
    selected_ids: tuple[str, ...]
    labels: tuple[str, ...]


def _options(frame: pd.DataFrame, column: str) -> list[str]:
    if column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).unique().tolist()
    return sorted(value for value in values if value.strip())


def _apply(frame: pd.DataFrame, column: str, selected: Iterable[str]) -> pd.DataFrame:
    choices = tuple(selected)
    if not choices or column not in frame.columns:
        return frame
    return frame[frame[column].astype(str).isin(choices)]


def project_filters(projects: pd.DataFrame, *, key_prefix: str) -> FilterResult:
    """Render project-only filters; these never imply product revenue ownership."""

    st.sidebar.subheader("Project scope")
    sidebar_scope_note(
        "Applies to delivery, engineering cost, testing, and project exception views."
    )
    filtered = projects.copy()
    labels: list[str] = []
    filter_specs = (
        ("engineering_team", "Engineering team"),
        ("category", "Project category"),
        ("status", "Project status"),
    )
    for column, label in filter_specs:
        selected = st.sidebar.multiselect(
            label, _options(filtered, column), key=f"{key_prefix}_{column}"
        )
        filtered = _apply(filtered, column, selected)
        if selected:
            labels.append(f"{label}: {', '.join(selected)}")

    names = _options(filtered, "project_name")
    if not names:
        names = _options(filtered, "name")
    name_column = "project_name" if "project_name" in filtered.columns else "name"
    selected_names = st.sidebar.multiselect("Project", names, key=f"{key_prefix}_project")
    filtered = _apply(filtered, name_column, selected_names)
    if selected_names:
        labels.append(f"Project: {', '.join(selected_names)}")

    ids = tuple(filtered.get("project_id", pd.Series(dtype=str)).dropna().astype(str))
    return FilterResult(filtered.reset_index(drop=True), ids, tuple(labels))


def product_filters(products: pd.DataFrame, *, key_prefix: str) -> FilterResult:
    """Render product-only filters, deliberately independent of engineering team."""

    st.sidebar.subheader("Product scope")
    sidebar_scope_note(
        "Applies to adoption, transactions, revenue, profit, and ROI. Revenue is not "
        "attributed to teams."
    )
    filtered = products.copy()
    labels: list[str] = []
    filter_specs = (
        ("product_owner", "Product owner"),
        ("category", "Product category"),
        ("lifecycle_status", "Lifecycle"),
    )
    for column, label in filter_specs:
        selected = st.sidebar.multiselect(
            label, _options(filtered, column), key=f"{key_prefix}_{column}"
        )
        filtered = _apply(filtered, column, selected)
        if selected:
            labels.append(f"{label}: {', '.join(selected)}")

    name_column = "product_name" if "product_name" in filtered.columns else "name"
    selected_names = st.sidebar.multiselect(
        "Product", _options(filtered, name_column), key=f"{key_prefix}_product"
    )
    filtered = _apply(filtered, name_column, selected_names)
    if selected_names:
        labels.append(f"Product: {', '.join(selected_names)}")

    ids = tuple(filtered.get("product_id", pd.Series(dtype=str)).dropna().astype(str))
    return FilterResult(filtered.reset_index(drop=True), ids, tuple(labels))


def related(frame: pd.DataFrame, id_column: str, selected_ids: Iterable[str]) -> pd.DataFrame:
    ids = tuple(selected_ids)
    if id_column not in frame.columns:
        return frame.copy()
    if not ids:
        return frame.iloc[0:0].copy()
    return frame[frame[id_column].astype(str).isin(ids)].copy()
