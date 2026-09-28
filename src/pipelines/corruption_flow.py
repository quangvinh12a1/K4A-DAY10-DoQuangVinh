from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe, save_clean_outputs
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import run_data_quality_checks
from observability.reporting import METRIC_LABELS, generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _save_corrupted(df: pd.DataFrame, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)


def _print_comparison(baseline: dict, corrupted: dict, repaired: dict, quality: dict[str, dict]) -> None:
    header = f"{'Metric':<24}{'Baseline':>12}{'Corrupted':>12}{'Repaired':>12}"
    print("\n" + header + "\n" + "-" * len(header))
    for key, label in METRIC_LABELS:
        print(f"{label[:23]:<24}{baseline[key]:>12.4f}{corrupted[key]:>12.4f}{repaired[key]:>12.4f}")
    print(f"{'GX success':<24}" + "".join(f"{str(quality[s]['success']):>12}" for s in ("baseline", "corrupted", "repaired")))
    print(
        f"{'is_fresh':<24}"
        + "".join(f"{str(quality[s]['freshness']['is_fresh']):>12}" for s in ("baseline", "corrupted", "repaired"))
        + "\n"
    )


def main() -> None:
    settings = load_settings()
    paths = settings.paths
    if not paths.baseline_metrics.exists() or not paths.clean_json.exists():
        raise RuntimeError("Baseline artifacts missing. Run `python script/run_phase1.py` first.")

    # 1. Baseline state.
    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_quality = read_json(paths.baseline_quality_report)
    clean_df = pd.read_json(paths.clean_json)

    # 2-3. Corrupt + save.
    corrupted_df = corrupt_clean_dataframe(clean_df, paths.corruption_log)
    _save_corrupted(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    print(f"[corruption] Injected 6 corruption types: {len(clean_df)} -> {len(corrupted_df)} rows.")

    # 5. Quality gate phat hien loi. Van index du lieu hong de do "silent failure" neu gate bi bo qua.
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    print(
        f"[corruption] Quality gate success={corrupted_quality['success']} "
        f"failed={corrupted_quality['failed_expectations']} | {corrupted_quality['freshness']['message']}"
    )

    # 4. Rebuild index + evaluate tren du lieu hong.
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_bundle = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    )

    # 6. Idempotent repair: tai tao tu raw snapshot, khong sua tay du lieu hong.
    repaired_df = build_clean_dataframe(load_raw_records(paths.raw_records_json), now_utc())
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    if not repaired_quality["success"]:
        raise RuntimeError(f"Repair failed quality gate: {repaired_quality['failed_expectations']}")
    save_clean_outputs(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    print(f"[repair] Rebuilt {len(repaired_df)} rows from raw snapshot; quality gate success={repaired_quality['success']}.")

    # 7. Evaluate repaired.
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_bundle = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    )

    # 8. Comparison report.
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_bundle.summary,
        repaired_bundle.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_quality["freshness"],
        repaired_quality["freshness"],
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_quality.get("freshness"),
        corruption_log=read_json(paths.corruption_log),
        answers_by_state={
            "Baseline": read_json(paths.baseline_answers),
            "Corrupted": corrupted_bundle.answers,
            "Repaired": repaired_bundle.answers,
        },
    )
    _print_comparison(
        baseline_metrics,
        corrupted_bundle.summary,
        repaired_bundle.summary,
        {"baseline": baseline_quality, "corrupted": corrupted_quality, "repaired": repaired_quality},
    )
    print(f"[corruption] Report -> {paths.comparison_report}")
