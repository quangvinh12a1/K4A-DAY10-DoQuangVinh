from __future__ import annotations

from pathlib import Path
from typing import Any

import great_expectations as gx
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MAX_STALE_RATIO = 0.25
REQUIRED_COLUMNS = ("paper_id", "title", "text_for_embedding")


def _build_expectations() -> list:
    expectations = [
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
        *[gx.expectations.ExpectColumnValuesToNotBeNull(column=column) for column in REQUIRED_COLUMNS],
        gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"),
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS),
    ]
    return expectations


def _summarize_result(result: Any) -> dict[str, Any]:
    config = result.expectation_config
    details = result.result or {}
    return {
        "expectation": config.type,
        "column": config.kwargs.get("column"),
        "success": bool(result.success),
        "observed_value": details.get("observed_value"),
        "unexpected_count": details.get("unexpected_count"),
        "unexpected_percent": details.get("unexpected_percent"),
        "partial_unexpected_list": [str(value) for value in details.get("partial_unexpected_list", [])][:5],
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    # GX 1.x: ephemeral context chay tren RAM, khong sinh file cau hinh.
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"{report_name}_papers_suite"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)
    validation = batch.validate(suite)

    checks = [_summarize_result(result) for result in validation.results]
    freshness_path = (
        settings.paths.freshness_report
        if report_name == "baseline"
        else settings.paths.quality_dir / f"{report_name}_freshness_report.json"
    )
    freshness = build_freshness_report(df, settings, freshness_path)
    gx_success = bool(validation.success)

    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "row_count": int(len(df)),
        "success": gx_success,
        "status": "FAIL" if not gx_success else ("WARN" if not freshness["is_fresh"] else "PASS"),
        "failed_expectations": [check["expectation"] for check in checks if not check["success"]],
        "checks": checks,
        "freshness": freshness,
    }
    write_json(settings.paths.quality_dir / f"{report_name}_quality_report.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    threshold = settings.freshness_threshold_days
    total_rows = int(len(df))
    published = pd.to_datetime(df["published"], errors="coerce") if total_rows else pd.Series(dtype="datetime64[ns]")
    ages = pd.to_numeric(df["age_days"], errors="coerce") if total_rows else pd.Series(dtype=float)

    stale_rows = int((ages > threshold).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    is_fresh = total_rows > 0 and stale_ratio <= MAX_STALE_RATIO

    payload = {
        "generated_at": now_utc().isoformat(),
        "latest_published": published.max().date().isoformat() if published.notna().any() else None,
        "oldest_published": published.min().date().isoformat() if published.notna().any() else None,
        "threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": bool(is_fresh),
        "message": (
            "Du lieu con tuoi."
            if is_fresh
            else f"CANH BAO: {stale_ratio:.0%} bai bao cu hon {threshold} ngay (> {MAX_STALE_RATIO:.0%}), can cap nhat du lieu moi."
        ),
    }
    write_json(Path(report_path), payload)
    return payload
