from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from core.utils import now_utc, write_text

METRIC_LABELS = [
    ("retrieval_hit_rate", "Retrieval Hit Rate"),
    ("mean_token_f1", "Mean Token F1"),
    ("judge_accuracy", "LLM Judge Accuracy"),
    ("mean_judge_score", "Mean Judge Score (1-5)"),
]


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.4f}"
    return "-" if value is None else str(value)


def _per_type_rows(answers: list[dict[str, Any]] | None) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in answers or []:
        grouped[item["question_type"]].append(item)
    return {
        question_type: {
            "n": len(items),
            "hit": mean(1.0 if item["retrieval_hit"] else 0.0 for item in items),
            "f1": mean(item["token_f1"] for item in items),
        }
        for question_type, items in sorted(grouped.items())
    }


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    lines = [
        "| Expectation | Column | Success | Observed / Unexpected |",
        "|---|---|:---:|---|",
    ]
    for check in quality.get("checks", []):
        observed = check.get("observed_value")
        if observed is None and check.get("unexpected_count") is not None:
            observed = f"{check['unexpected_count']} unexpected ({(check.get('unexpected_percent') or 0):.1f}%)"
        lines.append(
            f"| `{check['expectation']}` | {check.get('column') or '-'} | "
            f"{'PASS' if check['success'] else 'FAIL'} | {_fmt(observed)} |"
        )
    return lines


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
    answers: list[dict[str, Any]] | None = None,
) -> None:
    lines = [
        "# Phase 1 Report - Baseline Data Pipeline",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "## 1. Source & Lineage",
        "",
        "| Field | Value |",
        "|---|---|",
        *[f"| {key} | {_fmt(value)} |" for key, value in source_summary.items()],
        "",
        "## 2. Data Quality Gate (Great Expectations 1.x)",
        "",
        f"- **Overall success:** `{quality.get('success')}` (status `{quality.get('status')}`)",
        f"- **Rows validated:** {quality.get('row_count')}",
        "",
        *_quality_lines(quality),
        "",
        "## 3. Freshness SLA",
        "",
        f"- Latest published: `{freshness.get('latest_published')}` | Oldest published: `{freshness.get('oldest_published')}`",
        f"- Stale rows (age_days > {freshness.get('threshold_days')}): **{freshness.get('stale_rows')}/{freshness.get('total_rows')}** "
        f"({(freshness.get('stale_ratio') or 0):.0%}, max allowed {(freshness.get('max_stale_ratio') or 0):.0%})",
        f"- `is_fresh = {freshness.get('is_fresh')}` - {freshness.get('message')}",
        "",
        "## 4. Baseline RAG Evaluation",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Samples | {metrics.get('samples')} |",
        *[f"| {label} | {_fmt(metrics.get(key))} |" for key, label in METRIC_LABELS],
        "",
    ]
    per_type = _per_type_rows(answers)
    if per_type:
        lines += [
            "### Breakdown by question type",
            "",
            "| Question type | N | Hit Rate | Token F1 |",
            "|---|---:|---:|---:|",
            *[f"| {qt} | {row['n']} | {row['hit']:.2f} | {row['f1']:.2f} |" for qt, row in per_type.items()],
            "",
        ]
    ragas = metrics.get("ragas") or {}
    lines += ["### Ragas", "", f"`{ragas}`", ""]
    write_text(report_path, "\n".join(lines))


def _delta(after: Any, before: Any) -> str:
    if isinstance(after, (int, float)) and isinstance(before, (int, float)) and not isinstance(after, bool):
        return f"{after - before:+.4f}"
    return ""


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: dict[str, Any] | None = None,
    answers_by_state: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    baseline_quality = baseline_quality or {}
    baseline_freshness = baseline_freshness or {}

    lines = [
        "# Corruption Report - Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "## 1. RAG Metrics (3 states)",
        "",
        "| Metric | Baseline (clean) | Corrupted | Repaired | Delta corrupted | Delta repaired |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in METRIC_LABELS:
        base, bad, fixed = baseline_metrics.get(key), corrupted_metrics.get(key), repaired_metrics.get(key)
        lines.append(f"| {label} | {_fmt(base)} | {_fmt(bad)} | {_fmt(fixed)} | {_delta(bad, base)} | {_delta(fixed, base)} |")

    lines += [
        "",
        "## 2. Data Quality Gate & Freshness (3 states)",
        "",
        "| Signal | Baseline (clean) | Corrupted | Repaired |",
        "|---|---:|---:|---:|",
        f"| Rows | {_fmt(baseline_quality.get('row_count'))} | {_fmt(corrupted_quality.get('row_count'))} | {_fmt(repaired_quality.get('row_count'))} |",
        f"| GX success | {_fmt(baseline_quality.get('success'))} | {_fmt(corrupted_quality.get('success'))} | {_fmt(repaired_quality.get('success'))} |",
        f"| Failed expectations | {len(baseline_quality.get('failed_expectations', []))} | {len(corrupted_quality.get('failed_expectations', []))} | {len(repaired_quality.get('failed_expectations', []))} |",
        f"| Stale ratio | {_fmt(baseline_freshness.get('stale_ratio'))} | {_fmt(corrupted_freshness.get('stale_ratio'))} | {_fmt(repaired_freshness.get('stale_ratio'))} |",
        f"| is_fresh | {_fmt(baseline_freshness.get('is_fresh'))} | {_fmt(corrupted_freshness.get('is_fresh'))} | {_fmt(repaired_freshness.get('is_fresh'))} |",
        "",
        "### Corrupted data - GX detail",
        "",
        *_quality_lines(corrupted_quality),
        "",
    ]

    if corruption_log:
        lines += [
            "## 3. Injected Corruptions",
            "",
            f"Input rows: {corruption_log.get('input_rows')} -> output rows: {corruption_log.get('output_rows')} (seed `{corruption_log.get('seed')}`)",
            "",
            "| # | Corruption | Description | Affected rows |",
            "|---:|---|---|---:|",
            *[
                f"| {i} | `{item['corruption']}` | {item['description']} | {item['affected_rows']} |"
                for i, item in enumerate(corruption_log.get("corruptions", []), start=1)
            ],
            "",
        ]

    if answers_by_state:
        per_state = {state: _per_type_rows(answers) for state, answers in answers_by_state.items()}
        question_types = sorted({qt for rows in per_state.values() for qt in rows})
        states = list(per_state)
        lines += [
            "## 4. Token F1 by Question Type",
            "",
            "| Question type | " + " | ".join(states) + " |",
            "|---|" + "---:|" * len(states),
            *[
                f"| {qt} | " + " | ".join(f"{per_state[s].get(qt, {}).get('f1', 0.0):.2f}" for s in states) + " |"
                for qt in question_types
            ],
            "",
        ]

    hit_drop = (baseline_metrics.get("retrieval_hit_rate") or 0) - (corrupted_metrics.get("retrieval_hit_rate") or 0)
    f1_drop = (baseline_metrics.get("mean_token_f1") or 0) - (corrupted_metrics.get("mean_token_f1") or 0)
    recovered = all(
        abs((repaired_metrics.get(key) or 0) - (baseline_metrics.get(key) or 0)) < 1e-9
        for key in ("retrieval_hit_rate", "mean_token_f1")
    )
    lines += [
        "## 5. Analysis",
        "",
        f"- **Silent failure:** the pipeline raised no exception on corrupted data, yet Hit Rate dropped by "
        f"{hit_drop:.2f} and Token F1 dropped by {f1_drop:.2f}. The QA agent still answered confidently from wrong/missing context.",
        f"- **Detection:** the GX gate flagged the corrupted batch (`success = {corrupted_quality.get('success')}`, failed: "
        f"{', '.join(f'`{name}`' for name in corrupted_quality.get('failed_expectations', [])) or 'none'}) and the freshness monitor "
        f"reported `is_fresh = {corrupted_freshness.get('is_fresh')}` (stale ratio {(corrupted_freshness.get('stale_ratio') or 0):.0%}).",
        "- **Blind spots:** dropped newest records and noisy summaries do not violate any single expectation directly; "
        "they are only visible through row-count drift, freshness, and downstream metrics.",
        f"- **Repair:** re-running cleaning from the preserved raw snapshot (`data/raw/crossref_records.json`) is idempotent; "
        f"repaired metrics {'fully match' if recovered else 'do not fully match'} the baseline "
        f"and the repaired batch passes the gate (`success = {repaired_quality.get('success')}`).",
        "",
    ]
    write_text(report_path, "\n".join(lines))
