# Danh Sách Thành Viên & Báo Cáo Phân Công

- **Hình thức:** Bài làm cá nhân (1 thành viên đảm nhận toàn bộ 4 vai trò)
- **Họ tên / MSSV:** Đỗ Quang Vinh — 2A202602989
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** `K4A-DAY10-DoQuangVinh` — https://github.com/quangvinh12a1/K4A-DAY10-DoQuangVinh

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Đỗ Quang Vinh | 2A202602989 | [điền email] | Toàn bộ 4 vai trò: Pipeline Lead (`phase1.py`, `corruption_flow.py`), Data Foundation (`crossref.py`, `cleaning.py`, `corruption.py`), RAG & Vector Index (`retrieval/index.py`, ChromaDB), Observability & Evaluation (`quality.py`, `testset.py`, `reporting.py`) | [`report/2A202602989_DoQuangVinh.md`](../report/2A202602989_DoQuangVinh.md) |

### Phân công theo Checkpoint

| Checkpoint | Nội dung | Người thực hiện | Bằng chứng |
|---|---|---|---|
| CP0 | Fork repo, môi trường Python 3.12 + `pip install -e .`, `.env` | Đỗ Quang Vinh | Console `Môi trường sẵn sàng` |
| CP1 | Ingestion Crossref (dual-mode), cleaning, GX 1.x quality gate | Đỗ Quang Vinh | Commit `64da0d0`, `data/raw/`, `data/clean/`, `data/quality/baseline_quality_report.json` |
| CP2 | Test set 10 câu, ChromaDB `papers-baseline` | Đỗ Quang Vinh | `data/eval/test_set.json`, `data/embeddings/papers_embeddings.json` |
| CP3 | Baseline pipeline end-to-end, báo cáo Pha 1 | Đỗ Quang Vinh | Commit `bf2cf83`, `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| CP4 | 6 kịch bản corruption, đo suy giảm | Đỗ Quang Vinh | Commit `fae9b6d`, `data/results/corruption_log.json`, `corrupted_metrics.json` |
| CP5 | Idempotent repair, báo cáo 3 trạng thái | Đỗ Quang Vinh | `data/results/repaired_metrics.json`, `data/reports/corruption_report.md` |
| CP6 | Demo & nộp LMS | Đỗ Quang Vinh | Link repo trên VLearn LMS |

---

## # Cá nhân

### ## DoQuangVinh-2A202602989
- **Vai trò:** Thực hiện cá nhân toàn bộ pipeline (Pipeline Lead, Data Foundation Owner, RAG Specialist, Observability & Evaluation Lead).
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/crossref.py`: gọi Crossref REST API (retry 3 lần với backoff cho 429/5xx), tự động fallback sang snapshot `data/raw/crossref_response.json` khi mất mạng; chuẩn hóa DOI, bỏ thẻ JATS, parse ngày ISO 8601; fallback `categories` vì Crossref không còn trả `subject`.
  - `src/ingestion/cleaning.py`: chuẩn hóa text, tính `age_days`, sinh `text_for_embedding` 5 phần, khử trùng lặp theo `paper_id`, xuất CSV/JSON.
  - `src/observability/quality.py`: Quality Gate GX 1.x (`get_context(mode="ephemeral")`, `data_sources.add_pandas`) với 4 nhóm expectation + Freshness SLA (> 25% bài có `age_days > 180` → `is_fresh = False`).
  - `src/evaluation/testset.py`: 10 câu hỏi qua 5 dạng (`summary`, `authors`, `date`, `categories`, `multi_hop`).
  - `src/ingestion/corruption.py`: 6 kịch bản corruption có seed cố định và log chi tiết.
  - `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `src/observability/reporting.py`: điều phối 2 luồng và sinh báo cáo Markdown.
  - Sửa `src/retrieval/index.py` để manifest lưu đường dẫn Chroma tương đối (chạy được trên máy khác).
- **Công cụ hỗ trợ:** Có sử dụng trợ lý AI (Claude Code) để gợi ý và rà soát code theo chính sách AI tại `docs/RULES.md`; mọi kết quả đều được kiểm chứng bằng lệnh chạy thực tế và artifact trong repo.
- **Điều học được / Đóng góp chính:**
  - Dữ liệu hỏng không làm pipeline báo lỗi mà làm agent trả lời sai một cách tự tin (Silent Failure): Token F1 giảm 0.93 → 0.36 dù không có exception nào.
  - Quality gate chỉ bắt được lỗi vi phạm expectation (trùng `paper_id`, summary rỗng); các lỗi như mất bài mới được bù bằng dòng trùng lặp hay nhiễu trong `text_for_embedding` chỉ lộ ra qua metric hạ nguồn.
  - Giữ raw snapshot giúp repair idempotent: tái tạo từ raw cho kết quả trùng khớp 100% với baseline.
