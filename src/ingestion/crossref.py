from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from html import unescape
from pathlib import Path
import re
import time

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 20

_TAG_PATTERN = re.compile(r"<[^>]+>")
_DOI_PREFIX_PATTERN = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.IGNORECASE)


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _normalize_doi(value: str | None) -> str:
    doi = normalize_whitespace(value or "")
    return _DOI_PREFIX_PATTERN.sub("", doi).lower()


def _first_text(value) -> str:
    """Crossref tra ve title dang list; lay phan tu dau tien khong rong."""
    if isinstance(value, list):
        value = next((item for item in value if item), "")
    return normalize_whitespace(str(value or ""))


def _strip_markup(value: str | None) -> str:
    """Bo the HTML/JATS XML (vd `<jats:p>`) va decode HTML entities."""
    text = _TAG_PATTERN.sub(" ", value or "")
    return normalize_whitespace(unescape(text))


def _parse_authors(authors: list[dict] | None) -> list[str]:
    names: list[str] = []
    for author in authors or []:
        name = author.get("name") or " ".join(
            part for part in (author.get("given"), author.get("family")) if part
        )
        name = normalize_whitespace(name)
        if name:
            names.append(name)
    return names


def _parse_categories(item: dict) -> list[str]:
    """Crossref live API hien khong con tra `subject`; fallback sang group-title (linh vuc preprint),
    container-title (ten journal/venue), roi den loai tai lieu."""
    candidates = [
        item.get("subject"),
        [item.get("group-title")] if item.get("group-title") not in (None, "In Review") else None,
        item.get("container-title"),
        [str(item.get("type", "")).replace("-", " ").title()] if item.get("type") else None,
    ]
    for values in candidates:
        cleaned = [_strip_markup(str(value)) for value in values or [] if _strip_markup(str(value))]
        if cleaned:
            return list(dict.fromkeys(cleaned))
    return []


def _date_from_parts(field: dict | None) -> str:
    """Chuyen `{"date-parts": [[2026, 5, 20]]}` thanh ISO 8601 `2026-05-20`."""
    if not field:
        return ""
    if field.get("date-time"):
        return str(field["date-time"])[:10]
    parts = (field.get("date-parts") or [[]])[0] or []
    if not parts or parts[0] is None:
        return ""
    year, month, day = (list(parts) + [1, 1])[:3]
    return date(int(year), int(month or 1), int(day or 1)).isoformat()


def _pick_date(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return ""


def _pdf_url(item: dict, fallback: str) -> str:
    for link in item.get("link") or []:
        if "pdf" in str(link.get("content-type", "")).lower() and link.get("URL"):
            return link["URL"]
    return fallback


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for item in items:
        paper_id = _normalize_doi(item.get("DOI"))
        title = _strip_markup(_first_text(item.get("title")))
        summary = _strip_markup(item.get("abstract"))
        published = _pick_date(item, ("published", "published-print", "published-online", "issued", "created"))
        # Bo record khong du thong tin toi thieu de embed / tinh freshness.
        if not paper_id or not title or not summary or not published or paper_id in seen:
            continue
        seen.add(paper_id)

        categories = _parse_categories(item)
        abs_url = item.get("URL") or f"https://doi.org/{paper_id}"
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=_pick_date(item, ("updated", "deposited", "indexed", "created")) or published,
                abs_url=abs_url,
                pdf_url=_pdf_url(item, abs_url),
                comment=f"Crossref record {paper_id}",
            )
        )
    return records


def _request_crossref(settings: Settings) -> dict:
    # Sort theo relevance (mac dinh). Chan ngay xuat ban tuong lai de age_days khong bi am.
    params = {
        "query": settings.source_query,
        "filter": f"{settings.source_filter},until-pub-date:{date.today().isoformat()}",
        "rows": settings.max_results,
    }
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(CROSSREF_WORKS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(f"Crossref returned {response.status_code}", response=response)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Crossref API unavailable after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Dual-mode: goi Crossref API; neu loi (429, mat mang...) thi doc snapshot offline."""
    snapshot_path = settings.paths.raw_api_response
    records: list[PaperRecord] = []
    try:
        payload = _request_crossref(settings)
        records = parse_crossref_payload(payload)
        if not records:
            raise RuntimeError("Crossref API returned no usable records.")
        # Chi ghi de raw snapshot khi live API tra ve du lieu hop le.
        write_json(snapshot_path, payload)
        print(f"[crossref] Live API: {len(records)} records.")
    except RuntimeError as error:
        if not snapshot_path.exists():
            raise
        print(f"[crossref] {error} -> fallback to offline snapshot {snapshot_path.name}.")
        records = parse_crossref_payload(read_json(snapshot_path))

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    return [PaperRecord(**item) for item in read_json(path)]
