# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Đỗ Quang Vinh |
| MSSV | 2A202602989 |
| Khóa/Lớp | K4 — `K4-L3-DAY10` |
| Tên nhóm | Bài làm cá nhân |
| Vai trò chính | Thực hiện toàn bộ: source, data model, observability, corruption & integration |
| Repository | https://github.com/quangvinh12a1/K4A-DAY10-DoQuangVinh |
| Ngày hoàn thành | 2026-09-29 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Raw ingestion | `crossref.py`: `parse_crossref_payload`, `fetch_source_records`, `load_raw_records` | Crossref `/works` hoặc snapshot | `data/raw/crossref_response.json`, `crossref_records.json` | Hoàn thành |
| Cleaning | `cleaning.py`: `build_clean_dataframe`, `save_clean_outputs` | `list[PaperRecord]`, `run_date` | `data/clean/papers_clean.csv/json` | Hoàn thành |
| Quality & freshness | `quality.py`: `run_data_quality_checks`, `build_freshness_report` | DataFrame | `data/quality/*.json` | Hoàn thành |
| Evaluation set | `testset.py`: `build_test_set`, `load_or_create_test_set` | Clean DataFrame | `data/eval/test_set.json` | Hoàn thành |
| Corruption | `corruption.py`: `corrupt_clean_dataframe` | Clean DataFrame | `data/results/corruption_log.json`, `papers_clean_corrupted.*` | Hoàn thành |
| Orchestration & reporting | `phase1.py`, `corruption_flow.py`, `reporting.py` | Settings | Metrics, `phase1_report.md`, `corruption_report.md` | Hoàn thành |
| Ragas | `metrics.py::_run_ragas` (có sẵn) | Answers | — | Chưa chạy (hạn mức Gemini miễn phí) |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Sửa lưu đường dẫn Chroma tương đối | `src/retrieval/index.py` (code starter) | 3 manifest load được trên máy khác; không còn đường dẫn tuyệt đối trong repo |
| Chọn model LLM judge còn hạn mức | `.env.example` | Đổi sang `gemini-3.1-flash-lite`; 30/30 lượt judge dùng LLM thật, không fallback |

Có sử dụng trợ lý AI (Claude Code) để gợi ý và rà soát code theo `docs/RULES.md` mục 3; tôi đã chạy và kiểm chứng từng bước bằng lệnh và artifact nêu dưới đây.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Ingestion dual-mode | `src/ingestion/crossref.py` | 24 record | `Tín hiệu hoàn thành: Đã tải 24 bài báo`; giả lập mất mạng vẫn đọc snapshot 24 bài |
| Cleaning + `age_days` | `src/ingestion/cleaning.py` | 24 dòng sạch | `Tín hiệu hoàn thành: Clean thành công 24 dòng` |
| Quality gate GX 1.x | `src/observability/quality.py` | Baseline pass, corrupted fail | `Quality check status = True`; `data/quality/corrupted_quality_report.json` |
| Test set 10 câu | `src/evaluation/testset.py` | `data/eval/test_set.json` | 5 loại × 2 câu |
| 6 corruption + repair | `corruption.py`, `corruption_flow.py` | `data/reports/corruption_report.md` | `Corrupted 24 dòng`; repaired metrics = baseline |

Output cụ thể: `data/reports/corruption_report.md` — bảng 3 trạng thái cho thấy Hit Rate 1.00 → 0.60 → 1.00 và Token F1 0.93 → 0.36 → 0.93, kèm log 6 loại corruption và chi tiết expectation fail.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Đưa dữ liệu bài báo từ Crossref vào vector store sao cho (1) luôn giữ bản raw để tái tạo, (2) chặn dữ liệu xấu trước khi index, (3) đo được dữ liệu xấu làm RAG sai đến mức nào và chứng minh repair phục hồi.

### Cách triển khai

- **Ingestion:** gọi `/works` với filter `has-abstract:true`, khoảng ngày `[today-180d, today]`, sort theo relevance. Lần thử đầu sort theo ngày mới nhất trả về bài có ngày xuất bản ở tương lai (2027–2028) và lạc đề, nên tôi bỏ sort và thêm `until-pub-date`. Retry 3 lần cho 429/5xx; hết retry thì đọc snapshot, và chỉ ghi đè snapshot khi live API trả về dữ liệu hợp lệ.
- **Cleaning:** DOI viết thường làm `paper_id`, bỏ thẻ JATS bằng regex + `html.unescape`, parse ngày bằng `pd.to_datetime`, `age_days = (run_date - published).days`, dedupe giữ bản `updated` mới nhất.
- **Quality gate:** GX 1.x ephemeral context, 1 suite gồm 6 expectation (row count, 3 not-null, unique, summary length ≥ 30). Freshness tách riêng: tỉ lệ `age_days > 180` vượt 25% thì `is_fresh = False`. `phase1.py` raise lỗi và không index nếu gate fail.
- **Corruption:** 6 loại với `random.Random(42)`; số dòng nhân đôi bằng số bài bị drop để row count giữ nguyên, mô phỏng lỗi "tàng hình".
- **Repair:** không sửa dữ liệu hỏng mà tái tạo từ `crossref_records.json`, bắt buộc pass gate rồi mới index vào collection riêng `papers-repaired`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Crossref JSON (`message.items[]`) hoặc snapshot; `run_date` UTC |
| Output | DataFrame 16 cột (`paper_id`, `title`, `summary`, `authors`, `categories`, `published`, `age_days`, `text_for_embedding`, …); report dict có `success`, `failed_expectations`, `freshness` |
| Module phụ thuộc | `core/config.py` (paths, settings), `core/utils.py` |
| Module sử dụng output | `retrieval/index.py` (metadata Chroma), `evaluation/testset.py`, `evaluation/metrics.py` |
| Điều kiện lỗi cần xử lý | API 429/timeout, abstract rỗng, ngày thiếu tháng/ngày, record trùng DOI, thiếu `subject` |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** exit 0; baseline gate pass; corrupted gate fail và metric giảm; repaired metric bằng baseline.
- **Kết quả thực tế:** đúng như mong đợi (bảng ở mục 8).
- **Artifact/log:** `data/results/*_metrics.json`, `data/quality/*_quality_report.json`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `run_phase1.py` nên kéo dữ liệu mới từ Crossref mỗi lần chạy hay dùng raw snapshot đã lưu?
- **Các phương án đã cân nhắc:** (a) luôn gọi live API; (b) mặc định dùng snapshot, chỉ gọi API khi `REFRESH_SOURCE=1`.
- **Phương án đã chọn:** (b).
- **Lý do:** Crossref là nguồn sống; nếu mỗi lần chạy lấy dữ liệu khác thì `ground_truth_doc_ids` trong test set có thể không còn trong corpus và phép so sánh baseline/corrupted/repaired mất ý nghĩa. Snapshot cũng giúp chạy được khi mất mạng.
- **Bằng chứng quyết định phù hợp:** chạy lại baseline cho cùng 24 `paper_id` và cùng test set; repair từ snapshot cho `text_for_embedding` trùng khớp baseline.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `429 RESOURCE_EXHAUSTED ... Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash`; 8/10 câu baseline bị chấm bằng heuristic fallback.
- **Lệnh hoặc bước tái hiện:** `python script/run_phase1.py` với `LLM_MODEL=gemini-3.8-flash`.
- **Nguyên nhân gốc:** gói miễn phí giới hạn 20 request/ngày cho model đó, trong khi mỗi lần đánh giá cần 10 lượt judge + agent demo.
- **Cách xử lý:** liệt kê model khả dụng qua `google.genai`, thử structured output với `gemini-3.5-flash-lite` và `gemini-3.1-flash-lite`, chọn `gemini-3.1-flash-lite`; chạy lại baseline để cả 3 trạng thái cùng một judge.
- **Cách xác minh sau khi sửa:** đếm câu có reasoning chứa "Fallback" trong `baseline_answers.json`, `corrupted_answers.json`, `repaired_answers.json`: 0/30.
- **Điều học được:** metric do LLM chấm chỉ so sánh được khi cùng judge; phải kiểm tra judge có thực sự chạy hay đang rơi vào fallback.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Crossref trả JSON → lưu nguyên văn vào `crossref_response.json` → parse thành `PaperRecord` lưu `crossref_records.json` → cleaning ra DataFrame có `text_for_embedding` → quality gate → MiniLM chuyển `text_for_embedding` thành vector 384 chiều → ChromaDB lưu vector + metadata (title, authors, published, summary…).
2. Mỗi câu hỏi có `ground_truth_doc_ids` là DOI của bài dùng để sinh câu hỏi. Retrieval hit khi một trong top-4 DOI truy xuất nằm trong danh sách này; Token F1 so câu trả lời với `ground_truth`; LLM judge chấm độ đúng theo thang 1–5.
3. Quality checks kiểm tra cấu trúc và tính hợp lệ của từng batch (null, trùng, độ dài, số dòng). Freshness kiểm tra dữ liệu còn phản ánh hiện tại không — một batch có thể hợp lệ hoàn toàn nhưng đã cũ.
4. Nếu đổi test set giữa các trạng thái thì không biết metric thay đổi do dữ liệu hay do đề; giữ cố định test set là cách cô lập biến.
5. Repair thành công khi: `repaired_quality_report.json` có `success = True` và `is_fresh = True`, và `repaired_metrics.json` bằng `baseline_metrics.json` (Hit Rate 1.00, Token F1 0.9325, Judge 0.80).

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.00 | 0.60 | 1.00 | 4 câu miss đều hỏi về bài bị drop |
| `mean_token_f1` | 0.9325 | 0.3611 | 0.9325 | Giảm mạnh nhất ở `date` (1.00 → 0.00) |
| `judge_accuracy` | 0.80 | 0.30 | 0.80 | Baseline mất điểm ở `multi_hop` do QA top-1 |
| `mean_judge_score` | 4.5 | 2.3 | 4.5 | |
| Quality checks | Pass 6/6 | Fail 2/6 | Pass 6/6 | Fail: unique `paper_id`, summary length |
| Freshness status | Fresh (0%) | Stale (42%) | Fresh (0%) | |

### Kết luận từ số liệu

1. Drop 5 bài mới nhất + nhân đôi 5 dòng → row count vẫn 24 nên chỉ `paper_id` unique fail → Hit Rate 1.00 → 0.60 và agent trả lời bằng thông tin của bài khác (`eval_001`–`eval_004` trong `corrupted_answers.json`).
2. Repair từ raw snapshot → GX pass, `is_fresh = True` → 4 metric trở về đúng baseline.

Corruption ảnh hưởng rõ nhất là **drop latest records**: không expectation nào fail trực tiếp vì dòng trùng bù lại số lượng, nhưng nó gây toàn bộ 4 lần retrieval miss. **Stale date** đứng thứ hai: retrieval vẫn đúng bài nhưng câu `date` trả lời sai năm.

Kết quả khác kỳ vọng: tôi dự đoán nhiễu trong `text_for_embedding` và tiêu đề bị cắt sẽ làm retrieval sai, nhưng không có câu nào miss vì hai lỗi này. `eval_010` (bài bị chèn nhiễu) vẫn hit vì tiêu đề còn nguyên nên `qa.py` tra cứu chính xác theo tiêu đề; `eval_009` (bài bị cắt tiêu đề còn 8 ký tự) không tra cứu theo tiêu đề được nhưng semantic search vẫn tìm ra nhờ phần summary còn nguyên, Token F1 = 1.0. Kiểm chứng: đối chiếu `ground_truth_doc_ids` với `affected_paper_ids` trong `corruption_log.json` — 4 câu miss (`eval_001`–`eval_004`) đều thuộc `drop_latest_records`.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Giữ raw snapshot bất biến là điều kiện để repair idempotent và để benchmark có thể so sánh.
2. Quality gate chỉ thấy những gì được viết thành expectation; lỗi được "bù" (drop + duplicate) có thể lọt qua kiểm tra row count.
3. Dữ liệu sai không làm agent báo lỗi mà làm nó trả lời sai một cách tự tin — chỉ metric hạ nguồn mới lộ ra.

### Nếu có thêm thời gian

Thêm expectation đối chiếu tập `paper_id` của batch với raw records (phát hiện bài bị mất dù row count không đổi) và kiểm tra độ dài title tối thiểu; đo bằng số corruption bị gate phát hiện (hiện 3/6: duplicate, blank summary, stale date qua freshness).

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đỗ Quang Vinh
**Ngày xác nhận:** [YYYY-MM-DD]
