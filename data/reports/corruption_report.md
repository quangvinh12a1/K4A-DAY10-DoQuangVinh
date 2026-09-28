# Corruption Report - Baseline vs Corrupted vs Repaired

_Generated at 2026-09-28T18:33:26.299758+00:00_

## 1. RAG Metrics (3 states)

| Metric | Baseline (clean) | Corrupted | Repaired | Delta corrupted | Delta repaired |
|---|---:|---:|---:|---:|---:|
| Retrieval Hit Rate | 1.0000 | 0.6000 | 1.0000 | -0.4000 | +0.0000 |
| Mean Token F1 | 0.9325 | 0.3611 | 0.9325 | -0.5714 | +0.0000 |
| LLM Judge Accuracy | 0.8000 | 0.3000 | 0.8000 | -0.5000 | +0.0000 |
| Mean Judge Score (1-5) | 4.5000 | 2.3000 | 4.5000 | -2.2000 | +0.0000 |

## 2. Data Quality Gate & Freshness (3 states)

| Signal | Baseline (clean) | Corrupted | Repaired |
|---|---:|---:|---:|
| Rows | 24 | 24 | 24 |
| GX success | True | False | True |
| Failed expectations | 0 | 2 | 0 |
| Stale ratio | 0.0000 | 0.4167 | 0.0000 |
| is_fresh | True | False | True |

### Corrupted data - GX detail

| Expectation | Column | Success | Observed / Unexpected |
|---|---|:---:|---|
| `expect_table_row_count_to_be_between` | - | PASS | 24 |
| `expect_column_values_to_not_be_null` | paper_id | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_be_unique` | paper_id | FAIL | 10 unexpected (41.7%) |
| `expect_column_values_to_not_be_null` | title | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_not_be_null` | text_for_embedding | PASS | 0 unexpected (0.0%) |
| `expect_column_value_lengths_to_be_between` | summary | FAIL | 4 unexpected (16.7%) |

## 3. Injected Corruptions

Input rows: 24 -> output rows: 24 (seed `42`)

| # | Corruption | Description | Affected rows |
|---:|---|---|---:|
| 1 | `drop_latest_records` | Drop 20% newest papers. | 5 |
| 2 | `blank_summary` | Blank out summary text (empty scrape). | 3 |
| 3 | `truncate_title` | Truncate title to 8 characters (< 10). | 3 |
| 4 | `stale_published_date` | Shift published date back 5 years. | 8 |
| 5 | `inject_text_noise` | Insert garbage tokens into text_for_embedding. | 4 |
| 6 | `duplicate_rows` | Append duplicated rows (same paper_id). | 5 |

## 4. Token F1 by Question Type

| Question type | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| authors | 1.00 | 0.50 | 1.00 |
| categories | 1.00 | 0.50 | 1.00 |
| date | 1.00 | 0.00 | 1.00 |
| multi_hop | 0.66 | 0.31 | 0.66 |
| summary | 1.00 | 0.50 | 1.00 |

## 5. Analysis

- **Silent failure:** the pipeline raised no exception on corrupted data, yet Hit Rate dropped by 0.40 and Token F1 dropped by 0.57. The QA agent still answered confidently from wrong/missing context.
- **Detection:** the GX gate flagged the corrupted batch (`success = False`, failed: `expect_column_values_to_be_unique`, `expect_column_value_lengths_to_be_between`) and the freshness monitor reported `is_fresh = False` (stale ratio 42%).
- **Blind spots:** row count stayed at 24 (baseline 24) because duplicated rows masked the dropped newest records, so `expect_table_row_count_to_be_between` still passed; noise injected into `text_for_embedding` and truncated titles violate no expectation either. These are only visible through downstream metrics.
- **Repair:** re-running cleaning from the preserved raw snapshot (`data/raw/crossref_records.json`) is idempotent; repaired metrics fully match the baseline and the repaired batch passes the gate (`success = True`).
