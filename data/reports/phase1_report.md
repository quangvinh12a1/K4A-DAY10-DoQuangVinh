# Phase 1 Report - Baseline Data Pipeline

_Generated at 2026-09-28T18:25:06.289640+00:00_

## 1. Source & Lineage

| Field | Value |
|---|---|
| source_api | Crossref REST API |
| source_mode | raw snapshot (set REFRESH_SOURCE=1 to refetch) |
| query | agentic retrieval augmented generation large language model |
| filter | from-pub-date:2026-04-01,has-abstract:true |
| run_date | 2026-09-28 |
| raw_records | 24 |
| clean_rows | 24 |
| published_range | 2026-04-01 -> 2026-09-15 |
| embedding_model | sentence-transformers/all-MiniLM-L6-v2 |
| collection | papers-baseline |
| test_questions | 10 |
| llm_judge | gemini/gemini-3.1-flash-lite |

## 2. Data Quality Gate (Great Expectations 1.x)

- **Overall success:** `True` (status `PASS`)
- **Rows validated:** 24

| Expectation | Column | Success | Observed / Unexpected |
|---|---|:---:|---|
| `expect_table_row_count_to_be_between` | - | PASS | 24 |
| `expect_column_values_to_not_be_null` | paper_id | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_be_unique` | paper_id | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_not_be_null` | title | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_not_be_null` | text_for_embedding | PASS | 0 unexpected (0.0%) |
| `expect_column_value_lengths_to_be_between` | summary | PASS | 0 unexpected (0.0%) |

## 3. Freshness SLA

- Latest published: `2026-09-15` | Oldest published: `2026-04-01`
- Stale rows (age_days > 180): **0/24** (0%, max allowed 25%)
- `is_fresh = True` - Du lieu con tuoi.

## 4. Baseline RAG Evaluation

| Metric | Value |
|---|---:|
| Samples | 10 |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 0.9325 |
| LLM Judge Accuracy | 0.8000 |
| Mean Judge Score (1-5) | 4.5000 |

### Breakdown by question type

| Question type | N | Hit Rate | Token F1 |
|---|---:|---:|---:|
| authors | 2 | 1.00 | 1.00 |
| categories | 2 | 1.00 | 1.00 |
| date | 2 | 1.00 | 1.00 |
| multi_hop | 2 | 1.00 | 0.66 |
| summary | 2 | 1.00 | 1.00 |

### Ragas

`{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}`
