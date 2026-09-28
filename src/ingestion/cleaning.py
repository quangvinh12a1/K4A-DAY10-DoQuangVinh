from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.utils import compact_join, ensure_parent, normalize_whitespace, write_csv
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
]


def _normalize_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [normalize_whitespace(str(value)) for value in values if normalize_whitespace(str(value))]


def _build_embedding_text(row: pd.Series) -> str:
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Published: {row['published']}",
            f"Categories: {row['categories_joined']}",
            f"Summary: {row['summary']}",
        ]
    )


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    df = pd.DataFrame([asdict(record) for record in records])
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    # 1. Normalize text fields.
    for column in ("paper_id", "title", "summary", "primary_category", "abs_url", "pdf_url", "comment"):
        df[column] = df[column].fillna("").astype(str).map(normalize_whitespace)
    df["paper_id"] = df["paper_id"].str.lower()
    df["authors"] = df["authors"].map(_normalize_list)
    df["categories"] = df["categories"].map(_normalize_list)

    # 2. Parse dates (ISO 8601); dong khong parse duoc published se bi loai.
    published = pd.to_datetime(df["published"], errors="coerce")
    updated = pd.to_datetime(df["updated"], errors="coerce").fillna(published)
    df = df[published.notna()].copy()
    published, updated = published[df.index], updated[df.index]
    df["published"] = published.dt.strftime("%Y-%m-%d")
    df["updated"] = updated.dt.strftime("%Y-%m-%d")

    # 3. Freshness: age_days = (run_date - published).days
    run_day = pd.Timestamp(run_date.date())
    df["age_days"] = (run_day - published.dt.normalize()).dt.days.astype(int)

    # 4. Helper columns.
    df["authors_joined"] = df["authors"].map(compact_join)
    df["categories_joined"] = df["categories"].map(compact_join)
    df["summary_chars"] = df["summary"].str.len()
    df["text_for_embedding"] = df.apply(_build_embedding_text, axis=1)

    # 5. Filter bad rows va khu trung lap theo paper_id (giu ban cap nhat moi nhat).
    df = df[(df["paper_id"] != "") & (df["title"] != "") & (df["summary"] != "")]
    df = df.sort_values(["updated", "published"], ascending=False)
    df = df.drop_duplicates(subset="paper_id", keep="first")

    # 6. Sort on dinh: bai moi nhat truoc.
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]


def save_clean_outputs(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    """Luu clean data ra CSV (de doc) va JSON (giu nguyen kieu list cho authors/categories)."""
    write_csv(df, csv_path)
    ensure_parent(json_path)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)
