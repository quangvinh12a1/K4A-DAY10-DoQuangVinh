from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import load_or_create_test_set
from ingestion.cleaning import build_clean_dataframe, save_clean_outputs
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex

DEMO_QUESTIONS = 2


class DataQualityGateError(RuntimeError):
    """Chan du lieu xau truoc khi vao vector store."""


def _run_agent_demo(settings, index, test_set) -> None:
    try:
        from retrieval.agent import build_agent, run_agent_question

        agent = build_agent(settings, index)
        demo = [
            {"question": item["question"], "agent_answer": str(run_agent_question(agent, item["question"]))}
            for item in test_set[:DEMO_QUESTIONS]
        ]
    except Exception as error:  # demo khong duoc lam hong pipeline chinh
        demo = [{"error": f"Agent demo skipped: {error}"}]
    write_json(settings.paths.demo_answers, demo)


def main() -> None:
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()

    # 1-2. Raw ingestion (dual-mode). Mac dinh dung lai raw snapshot de benchmark on dinh;
    # REFRESH_SOURCE=1 de keo du lieu moi tu Crossref.
    if settings.refresh_source or not paths.raw_records_json.exists():
        records = fetch_source_records(settings)
        source_mode = "live Crossref API (fallback snapshot on failure)"
    else:
        records = load_raw_records(paths.raw_records_json)
        source_mode = "raw snapshot (set REFRESH_SOURCE=1 to refetch)"
    print(f"[phase1] Loaded {len(records)} raw records from {source_mode}.")

    # 3-4. Clean + persist.
    df = build_clean_dataframe(records, run_date)
    save_clean_outputs(df, paths.clean_csv, paths.clean_json)
    print(f"[phase1] Clean dataset: {len(df)} rows -> {paths.clean_csv.name}")

    # Quality gate truoc khi index: du lieu fail GX khong duoc vao Chroma.
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = quality["freshness"]
    print(f"[phase1] Quality gate success={quality['success']} status={quality['status']} | {freshness['message']}")
    if not quality["success"]:
        raise DataQualityGateError(f"Quality gate failed: {quality['failed_expectations']}")

    # 5. Index.
    index = LocalEmbeddingIndex.build(df, settings)
    print(f"[phase1] Chroma collection '{index.collection_name}' indexed {index.collection.count()} documents.")

    # 6-7. Test set + evaluate.
    test_set = load_or_create_test_set(df, paths.eval_testset, refresh=settings.refresh_test_set)
    bundle = evaluate_pipeline(settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers)
    metrics = bundle.summary
    print(
        f"[phase1] Baseline: hit_rate={metrics['retrieval_hit_rate']:.2f} token_f1={metrics['mean_token_f1']:.2f} "
        f"judge_accuracy={metrics['judge_accuracy']:.2f}"
    )

    # 9. Report.
    published = df["published"]
    source_summary = {
        "source_api": settings.source_api,
        "source_mode": source_mode,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "run_date": run_date.date().isoformat(),
        "raw_records": len(records),
        "clean_rows": len(df),
        "published_range": f"{published.min()} -> {published.max()}",
        "embedding_model": settings.embedding_model,
        "collection": index.collection_name,
        "test_questions": len(test_set),
        "llm_judge": f"{settings.llm_provider}/{settings.model_name}",
    }
    generate_phase1_report(paths.baseline_report, source_summary, metrics, quality, freshness, bundle.answers)
    print(f"[phase1] Report -> {paths.baseline_report}")

    # 10. Demo agent tren vai cau hoi.
    _run_agent_demo(settings, index, read_json(paths.eval_testset))
    print("[phase1] Done.")
