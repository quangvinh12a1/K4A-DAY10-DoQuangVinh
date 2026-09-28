# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 — `K4-L3-DAY10` |
| Tên nhóm | Bài làm cá nhân — Đỗ Quang Vinh |
| Repository | https://github.com/quangvinh12a1/K4A-DAY10-DoQuangVinh |
| Ngày hoàn thành | 2026-09-29 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Đỗ Quang Vinh | 2A202602989 | Toàn bộ (source, data model, observability, integration) | Toàn bộ `src/ingestion/`, `src/evaluation/testset.py`, `src/observability/`, `src/pipelines/`; sửa `src/retrieval/index.py` |

## 2. Tóm tắt kết quả

**Tóm tắt:**

Bài làm hoàn thành cả hai luồng. Luồng baseline (`script/run_phase1.py`) lấy 24 bài báo từ Crossref REST API, lưu raw response và raw records, làm sạch thành `data/clean/papers_clean.csv`, chạy Quality Gate Great Expectations 1.x (pass 6/6 expectation, freshness 0% bài cũ), nhúng bằng `all-MiniLM-L6-v2` vào ChromaDB collection `papers-baseline` và đánh giá trên bộ 10 câu hỏi cố định: Hit Rate 1.00, Token F1 0.93, Judge Accuracy 0.80.

Luồng corruption (`script/run_corruption_flow.py`) tiêm 6 lỗi. Ảnh hưởng rõ nhất là **drop latest records**: 4/10 câu hỏi nhắm vào bài bị mất nên retrieval trả về bài khác và agent trả lời sai tác giả/ngày/lĩnh vực một cách tự tin; kế đến là **stale date** làm cả hai câu `date` có Token F1 = 0. Tổng thể Hit Rate giảm 1.00 → 0.60, Token F1 0.93 → 0.36, Judge Accuracy 0.80 → 0.30. GX gate phát hiện trùng `paper_id` và summary rỗng, freshness báo 42% bài cũ.

Repair tái tạo dữ liệu từ raw snapshot, pass lại quality gate và phục hồi 100% cả 4 metric về đúng baseline. Giới hạn lớn nhất: QA extractive của starter chỉ trả lời từ tài liệu top-1 nên câu `multi_hop` bị judge chấm sai ngay cả ở baseline, và gói Gemini miễn phí có hạn mức thấp làm LLM judge chạy chậm.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (fallback: data/raw/crossref_response.json)
    -> data/raw/crossref_response.json + crossref_records.json      (crossref.py)
    -> data/clean/papers_clean.csv/json                             (cleaning.py)
    -> GX 1.x quality gate + freshness  -> data/quality/            (quality.py)  [fail => dừng, không index]
    -> MiniLM embedding + ChromaDB papers-baseline                  (retrieval/index.py)
    -> test set 10 câu -> evaluate -> data/results/baseline_*.json   (testset.py, metrics.py)
    -> data/reports/phase1_report.md                                (reporting.py)
    -> corruption 6 loại -> papers-corrupted -> evaluate            (corruption.py)
    -> repair từ raw records -> gate -> papers-repaired -> evaluate (corruption_flow.py)
    -> data/reports/corruption_report.md
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref `/works` hoặc snapshot | Fetch, retry 3 lần (backoff 2s/4s) cho 429/5xx, parse, fallback offline | `data/raw/crossref_response.json`, `crossref_records.json` | Đỗ Quang Vinh |
| Cleaning | `list[PaperRecord]`, `run_date` | Chuẩn hóa text, parse ngày, `age_days`, `text_for_embedding`, dedupe | `data/clean/papers_clean.csv/json` | Đỗ Quang Vinh |
| Embedding/index | Clean DataFrame | MiniLM-L6-v2, Chroma cosine, 3 collection tách biệt | `data/chroma/`, `data/embeddings/*.json` | Đỗ Quang Vinh |
| Evaluation | Clean DataFrame, index | 10 câu hỏi, Hit Rate, Token F1, LLM judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Đỗ Quang Vinh |
| Observability | DataFrame | GX 1.x 6 expectation + freshness SLA | `data/quality/*.json` | Đỗ Quang Vinh |
| Corruption/repair | Clean DataFrame / raw records | 6 corruption (seed 42), repair từ raw | `corruption_log.json`, `papers_clean_corrupted/repaired.*` | Đỗ Quang Vinh |
| Orchestration | Settings | Thứ tự chạy 2 flow, quality gate chặn index | `data/reports/*.md` | Đỗ Quang Vinh |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `gemini` |
| `LLM_MODEL` | `gemini-3.1-flash-lite` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results = 24`) |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày, tối đa 25% bài cũ |
| Random seed | 42 (corruption) |

### Lệnh cài đặt

Python 3.12 (project yêu cầu `>=3.11,<3.14`):

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

Mặc định `run_phase1.py` dùng raw snapshot đã lưu để benchmark ổn định; đặt `REFRESH_SOURCE=1` để kéo dữ liệu mới từ Crossref.

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (exit 0, 256 giây) | 2026-09-29 | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow | Thành công (exit 0, 220 giây) | 2026-09-29 | `data/results/corrupted_metrics.json`, `repaired_metrics.json`, `data/reports/corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | `https://api.crossref.org/works` |
| Query/filter | query `agentic retrieval augmented generation large language model`; filter `from-pub-date:<today-180d>,has-abstract:true,until-pub-date:<today>`; sort theo relevance |
| Thời điểm lấy dữ liệu | 2026-09-29 (UTC+7) |
| Số record nhận được | 24 item (tổng khớp truy vấn trên Crossref: 101,635) → 24 record hợp lệ |
| Cơ chế retry/backoff | 3 lần, backoff 2s rồi 4s cho 429/500/502/503/504 và lỗi mạng; hết retry thì đọc snapshot offline |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str | Có | DOI chuẩn hóa (lowercase, bỏ `https://doi.org/`) | Thiếu → bỏ record; trùng → giữ bản `updated` mới nhất |
| `title` | str | Có | Tiêu đề, bỏ thẻ HTML, chuẩn hóa khoảng trắng | Thiếu → bỏ record |
| `summary` | str | Có | Abstract đã bỏ thẻ JATS (`<jats:p>`) | Thiếu → bỏ record |
| `authors` | list[str] | Không | `given family` hoặc `name` | Thiếu → list rỗng |
| `categories` | list[str] | Không | `subject` → `group-title` → `container-title` → `type` | Fallback theo thứ tự |
| `published` | str ISO `YYYY-MM-DD` | Có | Ngày xuất bản | Không parse được → bỏ record |
| `age_days` | int | Có | `(run_date - published).days` | Tính từ `published` |
| `text_for_embedding` | str | Có | Title/Authors/Published/Categories/Summary | Sinh từ các cột trên |

### Quy tắc cleaning

| Quy tắc | Quality dimension liên quan | Số record bị tác động | Cách xác minh |
| --- | --- | ---: | --- |
| Bỏ thẻ JATS/HTML khỏi abstract | Validity | 17 | So sánh `crossref_response.json` với `crossref_records.json` |
| Fallback `categories` khi thiếu `subject` | Completeness | 24 (container 15, type 7, group-title 2) | `categories_joined` không rỗng ở 24/24 dòng |
| Loại record thiếu DOI/title/abstract/ngày | Completeness | 0 | 24 raw → 24 clean |
| Dedupe theo `paper_id` | Uniqueness | 0 | GX `expect_column_values_to_be_unique` pass |

`text_for_embedding` ghép 5 dòng `Title / Authors / Published / Categories / Summary` để embedding chứa cả metadata lẫn nội dung. Document ID là DOI chuẩn hóa nên ổn định giữa các lần chạy; Chroma record ID là `<paper_id>::<index>` để vẫn nạp được khi có dòng trùng ở trạng thái corrupted. `age_days` tính theo ngày chạy pipeline để freshness phản ánh đúng thời điểm serving.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 10 |
| Các `question_type` | `summary`, `authors`, `date`, `categories`, `multi_hop` (mỗi loại 2 câu) |
| Ground-truth document ID | DOI của bài dùng để sinh câu hỏi (`multi_hop`: 2 DOI) |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB cosine: `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k` | 4 |
| LLM provider/model | Gemini `gemini-3.1-flash-lite` (judge + agent demo) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (SHA-256 bắt đầu `794D95BDC33A`) |

Test set được sinh một lần từ dữ liệu sạch và `load_or_create_test_set` tái sử dụng file này; `corruption_flow.py` đánh giá cả 3 trạng thái trên cùng file. Nhờ vậy mọi thay đổi metric chỉ đến từ dữ liệu, không đến từ đề thi.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | 24 item từ live API |
| Cleaned dataset | `data/clean/` | Có | 24 dòng |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 3 collection × 24 docs, đường dẫn tương đối |
| Evaluation set | `data/eval/` | Có | 10 câu |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | |
| Quality/freshness | `data/quality/` | Có | baseline/corrupted/repaired + `freshness_report.json` |
| Baseline report | `data/reports/phase1_report.md` | Có | |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 10/10 câu truy xuất được đúng DOI trong top-4 (câu hỏi chứa tiêu đề nên lookup chính xác) |
| `mean_token_f1` | 0.9325 | 8 câu khớp tuyệt đối; 2 câu `multi_hop` F1 ≈ 0.66 vì chỉ trả lời 1/2 bài |
| `judge_accuracy` | 0.8000 | Judge đánh sai đúng 2 câu `multi_hop` ("only addresses the first paper") |
| `mean_judge_score` | 4.5000 | 8 câu 5/5, `multi_hop` được 3 và 2 |
| Ragas | N/A | Không chạy (`RUN_RAGAS` chưa bật) do hạn mức Gemini miễn phí |

## 8. Data quality và freshness

### Quality checks

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `ExpectTableRowCountToBeBetween` | Volume | 5 – 5000 dòng | Pass (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` × 3 | Completeness | `paper_id`, `title`, `text_for_embedding` không null | Pass (0 unexpected) | như trên |
| `ExpectColumnValuesToBeUnique` | Uniqueness | `paper_id` duy nhất | Pass (0 unexpected) | như trên |
| `ExpectColumnValueLengthsToBeBetween` | Validity | `summary` ≥ 30 ký tự | Pass (0 unexpected) | như trên |

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Clean dataset trước khi index (`age_days`) |
| Timestamp mới nhất | 2026-09-15 (cũ nhất 2026-04-01) |
| Ngưỡng freshness | `age_days > 180` là stale; tối đa 25% stale |
| Trạng thái baseline | Fresh |
| Lý do | 0/24 bài vượt 180 ngày (bài cũ nhất đúng 180 ngày) |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | ---: | --- | --- | --- |
| `drop_latest_records` | Bỏ 20% bài mới nhất | 5 | Row count / freshness | Row count vẫn 24 (bị dòng trùng che); 4 câu hỏi về bài bị mất → retrieval miss, agent trả lời bằng bài khác | Tái tạo từ raw |
| `blank_summary` | Summary = "" | 3 | `summary` length fail | GX fail (4 dòng tính cả dòng trùng); `eval_005` trả lời rỗng | Tái tạo từ raw |
| `truncate_title` | Title còn 8 ký tự | 3 | Không có expectation trực tiếp | Không bị GX phát hiện | Tái tạo từ raw |
| `stale_published_date` | Lùi 5 năm | 8 | Freshness | `is_fresh = False` (42% stale); cả 2 câu `date` F1 = 0 | Tái tạo từ raw |
| `inject_text_noise` | Chèn token rác vào `text_for_embedding` | 4 | Không có expectation trực tiếp | Không bị GX phát hiện | Tái tạo từ raw |
| `duplicate_rows` | Nhân đôi số dòng bằng số bài bị drop | 5 | `paper_id` unique fail | GX fail (10 giá trị trùng) | Tái tạo từ raw + dedupe |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đủ 6 loại, mô tả tham số, số dòng và danh sách `paper_id` bị tác động, seed 42 và row count trước/sau (24 → 24).

Repair không vá từng dòng hỏng mà chạy lại `build_clean_dataframe` từ `data/raw/crossref_records.json`, nguồn raw được giữ nguyên từ lúc ingest. Dữ liệu repaired phải pass quality gate thì mới được index (`corruption_flow.py` raise nếu fail). Đã kiểm chứng: chạy repair 2 lần cho DataFrame giống hệt nhau, và `text_for_embedding` + thứ tự `paper_id` của bản repaired trùng khớp bản baseline.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.00 | 0.60 | 1.00 | −0.40 | 100% | 4 câu miss đều hỏi bài bị drop |
| `mean_token_f1` | 0.9325 | 0.3611 | 0.9325 | −0.5714 | 100% | `date` về 0 do stale date |
| `judge_accuracy` | 0.80 | 0.30 | 0.80 | −0.50 | 100% | |
| `mean_judge_score` | 4.5 | 2.3 | 4.5 | −2.2 | 100% | |
| Quality checks pass/fail | Pass | Fail (2 expectation) | Pass | unique + summary length fail | Pass lại | Row count vẫn pass |
| Freshness status | Fresh (0%) | Stale (42%) | Fresh (0%) | +42% stale | Phục hồi | |

Kết luận nhân quả:

1. Drop 5 bài mới nhất và nhân đôi 5 dòng khác → row count vẫn 24 nên `ExpectTableRowCountToBeBetween` pass, chỉ `paper_id` unique fail → 4 câu hỏi về bài bị drop retrieval miss (Hit Rate 1.00 → 0.60) và agent vẫn trả về tác giả/ngày/lĩnh vực của bài khác (`data/results/corrupted_answers.json`, `eval_001`–`eval_004`).
2. Lùi `published` 5 năm cho 8 bài → freshness `is_fresh = False` (42% stale) → câu `eval_008` vẫn retrieve đúng bài nhưng trả lời `2021-08-14`, Token F1 của nhóm `date` về 0.
3. Repair từ raw snapshot → GX pass, `is_fresh = True` → cả 4 metric trở về đúng giá trị baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Manifest `data/embeddings/*.json` lưu `persist_path` là đường dẫn tuyệt đối trên máy cá nhân; clone repo sang máy khác thì `LocalEmbeddingIndex.load()` không tìm thấy ChromaDB. Ngoài ra lần chạy đầu `categories_joined` rỗng ở mọi dòng.
- **Nguyên nhân:** `index.py` ghi `str(persist_path)`; Crossref live API hiện không trả trường `subject`.
- **Cách xử lý:** Lưu `persist_path` tương đối với project root và resolve lại khi load; fallback `categories` sang `group-title` / `container-title` / `type`.
- **Cách xác minh:** Load lại cả 3 manifest và search thành công trên `papers-baseline`, `papers-corrupted`, `papers-repaired`; quét repo không còn đường dẫn tuyệt đối; 24/24 dòng có `categories_joined`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| QA extractive chỉ trả lời từ tài liệu top-1 | `multi_hop` bị judge chấm sai ở cả baseline (F1 ≈ 0.66) | Ghép câu trả lời từ các tài liệu khớp tiêu đề; đo lại judge accuracy của `multi_hop` |
| GX không bắt được drop/noise/truncate khi row count được bù | Lỗi "tàng hình" chỉ lộ qua metric | Thêm expectation so sánh tập `paper_id` với raw, độ dài title tối thiểu, tỉ lệ ký tự không phải chữ trong `text_for_embedding` |
| Hạn mức Gemini miễn phí thấp | `gemini-3.8-flash` hết hạn mức sau 20 request; judge có lúc chậm do rate limit; Ragas chưa chạy | Cache kết quả judge theo (question, answer) hoặc dùng provider có hạn mức cao hơn |
| Crossref là nguồn sống | Số liệu thay đổi mỗi lần `REFRESH_SOURCE=1` | Giữ snapshot đã commit làm benchmark cố định |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
