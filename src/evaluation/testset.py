from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, read_json, write_json

MIN_DOCUMENTS = 5
QUESTIONS_PER_TYPE = 2
QUESTION_TYPES = ("summary", "authors", "date", "categories", "multi_hop")
REQUIRED_KEYS = ("id", "type", "question_type", "question", "ground_truth", "ground_truth_doc_ids")

# Cau hoi tieng Anh, khop keyword ma `retrieval/qa.py::_extract_answer` nhan dien.
TEMPLATES = {
    "summary": "What is the summary of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
    "multi_hop": "Compare the papers '{title}' and '{other_title}': what does each study focus on?",
}


def _has_value(row: pd.Series, column: str) -> bool:
    return bool(str(row.get(column) or "").strip())


def _eligible(row: pd.Series, question_type: str) -> bool:
    if question_type == "authors":
        return _has_value(row, "authors_joined")
    if question_type == "categories":
        return _has_value(row, "categories_joined")
    return _has_value(row, "summary")


def _ground_truth(row: pd.Series, question_type: str, other: pd.Series | None = None) -> str:
    if question_type == "authors":
        return str(row["authors_joined"])
    if question_type == "date":
        return str(row["published"])
    if question_type == "categories":
        return str(row["categories_joined"])
    if question_type == "multi_hop" and other is not None:
        return f"{first_sentence(row['summary'])} {first_sentence(other['summary'])}"
    return first_sentence(row["summary"])


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} documents to build a test set, got {len(df)}.")

    rows = [row for _, row in df.reset_index(drop=True).iterrows()]
    usage = {str(row["paper_id"]): 0 for row in rows}
    test_set: list[dict[str, Any]] = []

    def pick(question_type: str, exclude: set[str]) -> pd.Series | None:
        # Uu tien paper duoc dung it nhat -> phu rong corpus, deterministic theo thu tu df.
        candidates = [r for r in rows if _eligible(r, question_type) and r["paper_id"] not in exclude]
        if not candidates:
            return None
        chosen = min(candidates, key=lambda r: usage[str(r["paper_id"])])
        usage[str(chosen["paper_id"])] += 1
        return chosen

    for round_index in range(QUESTIONS_PER_TYPE):
        for question_type in QUESTION_TYPES:
            row = pick(question_type, exclude=set())
            if row is None:
                continue
            other = pick("multi_hop", exclude={row["paper_id"]}) if question_type == "multi_hop" else None
            if question_type == "multi_hop" and other is None:
                continue
            doc_ids = [str(row["paper_id"])] + ([str(other["paper_id"])] if other is not None else [])
            test_set.append(
                {
                    "id": f"eval_{len(test_set) + 1:03d}",
                    "type": question_type,
                    "question_type": question_type,
                    "question": TEMPLATES[question_type].format(
                        title=row["title"], other_title=other["title"] if other is not None else ""
                    ),
                    "ground_truth": _ground_truth(row, question_type, other),
                    "ground_truth_doc_ids": doc_ids,
                }
            )

    write_json(Path(output_path), test_set)
    return test_set


def load_or_create_test_set(df: pd.DataFrame, output_path, refresh: bool = False) -> list[dict[str, Any]]:
    """Dung lai test set da co (giu benchmark on dinh giua cac lan chay); tao moi neu thieu/hong."""
    path = Path(output_path)
    if not refresh and path.exists():
        try:
            existing = read_json(path)
            known_ids = set(df["paper_id"].astype(str))
            if existing and all(
                all(key in item for key in REQUIRED_KEYS) and set(item["ground_truth_doc_ids"]) <= known_ids
                for item in existing
            ):
                return existing
        except (ValueError, KeyError, TypeError):
            pass
    return build_test_set(df, path)
