from __future__ import annotations

import math
import random

import pandas as pd

from core.utils import now_utc, write_json

SEED = 42
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_RATIO = 0.15
NOISE_RATIO = 0.15
TRUNCATE_TITLE_RATIO = 0.15
STALE_DATE_RATIO = 0.40
DUPLICATE_RATIO = 0.20
STALE_SHIFT_DAYS = 365
TITLE_MAX_CHARS = 7
NOISE_TOKENS = ["#@!%", "��", "lorem", "NULL", "<br/>", "&amp;&amp;", "xX9$q"]


def _rebuild_embedding_text(row: pd.Series) -> str:
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Published: {row['published']}",
            f"Categories: {row['categories_joined']}",
            f"Summary: {row['summary']}",
        ]
    )


def _sample(rng: random.Random, index: list[int], ratio: float) -> list[int]:
    count = max(1, math.ceil(len(index) * ratio))
    return sorted(rng.sample(index, min(count, len(index))))


def _inject_noise(text: str, rng: random.Random) -> str:
    words = text.split()
    for _ in range(max(3, len(words) // 4)):
        words.insert(rng.randrange(len(words) + 1), rng.choice(NOISE_TOKENS))
    return " ".join(words)


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Tiem 6 dang loi co kiem soat (deterministic theo SEED) va ghi corruption log."""
    rng = random.Random(SEED)
    corrupted = df.copy().reset_index(drop=True)
    log: list[dict] = []

    def record(kind: str, description: str, rows: pd.DataFrame) -> None:
        log.append(
            {
                "corruption": kind,
                "description": description,
                "affected_rows": int(len(rows)),
                "affected_paper_ids": rows["paper_id"].astype(str).tolist(),
            }
        )

    # 1. Drop latest records: mat 20% bai moi nhat (ingestion fail -> stale knowledge).
    latest = corrupted.sort_values("published", ascending=False).head(math.ceil(len(corrupted) * DROP_LATEST_RATIO))
    record("drop_latest_records", f"Drop {DROP_LATEST_RATIO:.0%} newest papers.", latest)
    corrupted = corrupted.drop(index=latest.index).reset_index(drop=True)
    remaining = list(corrupted.index)

    # 2. Blank summary.
    rows = _sample(rng, remaining, BLANK_SUMMARY_RATIO)
    record("blank_summary", "Blank out summary text (empty scrape).", corrupted.loc[rows])
    corrupted.loc[rows, "summary"] = ""

    # 3. Inject noise vao summary (chon trong cac dong chua bi blank).
    rows = _sample(rng, [i for i in remaining if corrupted.at[i, "summary"]], NOISE_RATIO)
    record("inject_noise", "Insert garbage tokens into summary.", corrupted.loc[rows])
    for i in rows:
        corrupted.at[i, "summary"] = _inject_noise(corrupted.at[i, "summary"], rng)

    # 4. Truncate title < 8 ky tu.
    rows = _sample(rng, remaining, TRUNCATE_TITLE_RATIO)
    record("truncate_title", f"Truncate title to {TITLE_MAX_CHARS} characters.", corrupted.loc[rows])
    corrupted.loc[rows, "title"] = corrupted.loc[rows, "title"].str.slice(0, TITLE_MAX_CHARS)

    # 5. Stale date: lui published ve 365 ngay truoc.
    rows = _sample(rng, remaining, STALE_DATE_RATIO)
    record("stale_published_date", f"Shift published date back {STALE_SHIFT_DAYS} days.", corrupted.loc[rows])
    shifted = pd.to_datetime(corrupted.loc[rows, "published"]) - pd.Timedelta(days=STALE_SHIFT_DAYS)
    corrupted.loc[rows, "published"] = shifted.dt.strftime("%Y-%m-%d")
    corrupted.loc[rows, "age_days"] = corrupted.loc[rows, "age_days"].astype(int) + STALE_SHIFT_DAYS

    # 6. Duplicate rows.
    rows = _sample(rng, remaining, DUPLICATE_RATIO)
    record("duplicate_rows", "Append duplicated rows (same paper_id).", corrupted.loc[rows])
    corrupted = pd.concat([corrupted, corrupted.loc[rows]], ignore_index=True)

    # 7. Rebuild derived columns de loi lan vao embedding (silent failure).
    corrupted["summary_chars"] = corrupted["summary"].str.len()
    corrupted["text_for_embedding"] = corrupted.apply(_rebuild_embedding_text, axis=1)

    write_json(
        output_log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": SEED,
            "input_rows": int(len(df)),
            "output_rows": int(len(corrupted)),
            "corruptions": log,
        },
    )
    return corrupted
