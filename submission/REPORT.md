# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Hoàng Văn Tài
- **MSSV:** 2A202602400
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/htai2329102003-web/K4-L3-DAY13-HoangVanTai-2A202602400-Monitoring-LLMOps
- **Commit SHA cuối:** 13b606680ae4a3072eda90334959b632fe4ecba0
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602400`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [evidence/01-pytest.txt](evidence/01-pytest.txt) |
| Log validator | [evidence/02-log-validator.png](evidence/02-log-validator.png) |
| Dashboard validator | [evidence/03-dashboard-validator.png](evidence/03-dashboard-validator.png) |
| Structured log | [evidence/04-structured-log.png](evidence/04-structured-log.png) |
| PII redaction | [evidence/05-pii-redaction.png](evidence/05-pii-redaction.png) |
| Trace list | [evidence/06-trace-list.png](evidence/06-trace-list.png) |
| Trace waterfall | [evidence/07-trace-waterfall.png](evidence/07-trace-waterfall.png) |
| Trace metadata | [evidence/08-trace-metadata.png](evidence/08-trace-metadata.png) |
| Prompt versions | [evidence/09-prompt-versions.png](evidence/09-prompt-versions.png) |
| Prompt rollback | [evidence/10-prompt-rollback.png](evidence/10-prompt-rollback.png) |
| Dashboard runtime | [evidence/11-dashboard-overview.png](evidence/11-dashboard-overview.png) |
| Incident metric | [evidence/12-incident-metric.png](evidence/12-incident-metric.png) |
| Incident log | [evidence/13-incident-log.png](evidence/13-incident-log.png) |
| Incident trace | [evidence/14-incident-trace.png](evidence/14-incident-trace.png) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100; 62 log records; 60 missing required fields; 60 missing enrichment fields; 0 correlation IDs; 0 PII hits | 100/100; 151 log records; 0 missing required fields/enrichment; 73 unique correlation IDs; 0 PII hits | |
| `validate_dashboard.py` | HỢP LỆ: 6/6 panel | HỢP LỆ: 6/6 panel | |
| `pytest` | 22 passed in 2.05s | 25 passed in 2.43s | |
| Số traces hợp lệ | 0 trace hợp lệ| 31/31 traces trong 60 phút có root, retrieval, generation và correlation ID; 21 trace dùng managed prompt `day13-chat` | |
| Số PII leak | 0 | 0 | |
| Latency P95 / TTFT P95 | 1725.0 ms / 52.0 ms | 1549.05 ms / 50.0 ms (10 response log của workload CP2, concurrency 5) | |
| Retrieval success rate | 100% (30/30) | 100% (10/10 response log của workload CP2) | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware nhận `x-request-id` hợp lệ hoặc sinh `req-<8-hex>`, bind ID vào log context, lưu trong request state và trả lại qua `x-request-id`; response có thêm `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `user_id_hash` (SHA-256 rút gọn), `session_id`, `feature`, `model`, `env`, cùng `ts`, `level`, `service`, `event` và `correlation_id`.
- **Cách bảo đảm PII được scrub trước khi ghi:** Structlog scrub đệ quy các chuỗi sau bước format exception và trước JSONL writer/JSON renderer; che email, điện thoại VN, CCCD và số thẻ.
- **Cách kiểm chứng kết quả:** Log validator đạt 100/100 trên 22 dòng CP1; không thiếu trường hoặc metadata, có 11 correlation ID và không phát hiện PII. Sáu test liên quan đến PII/logging đạt.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Đã kiểm tra Langfuse Observations API trong project đang cấu hình: 31/31 root trace trong 60 phút có đủ child `retrieval`/`llm-generation` và `correlation_id`; các trace CP2 được đối chiếu với log theo ID này.
- **Cấu trúc root/retrieval/generation observations:** Root `lab-agent-run` chứa child `retrieval` kiểu `retriever` và `llm-generation` kiểu `generation`; generation ghi model, prompt version, token usage và cost.
- **Cách nối trace với log:** `correlation_id` được propagate vào trace metadata và ghi trong JSONL của cùng request.
- **Prompt name:** `day13-chat`.
- **Version/label baseline:** v1 / `baseline` (managed Langfuse).
- **Version/label candidate:** v2 / `candidate` (managed Langfuse).
- **Trace ID của mỗi version:** baseline v1 `fb7a711b6172bcfbf802518b3abe0c8d` (`cp2-verify-baseline-0929`); candidate v2 `c89c374a67a11c9d51a758bef8e21492` (`cp2-verify-candidate-0929`); cùng input, cả hai HTTP 200, `prompt_source=langfuse`.
- **Cách promote và rollback `production`:** Đã chuyển `production` sang v2 và chạy cùng input thành công: trace `adcc02ceadb10516785f8d9f9d6246a3`, version 2. Sau đó rollback `production` về v1 và chạy lại thành công: trace `8b619d1b2b5e7c91b21f5ffc0b3a9bd3`, version 1. Đã đọc lại label cuối: `baseline`=v1, `candidate`=v2, `production`=v1. Lưu ảnh trạng thái trước/sau rollback.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Dashboard cục bộ tại `http://127.0.0.1:8501/`, đọc `data/logs.jsonl`, refresh 30 giây và hiển thị latency/TTFT, traffic, errors/retrieval, cost, tokens, quality.
- **SLO và lý do chọn:** 99.5% request hoàn tất trong 3000 ms trên cửa sổ 28 ngày; threshold 3 giây bám theo latency SLI.
- **Cách tính error budget:** 0.5% tổng `request_received` trong cùng 28 ngày được phép lỗi hoặc vượt 3000 ms; theo dõi số request xấu chia tổng request.
- **Ba alert và runbook tương ứng:** Error rate >2%/5m (`docs/alerts.md#alert-1`); latency P95 >3000 ms/10m (`#alert-2`); retrieval success <90%/5m (`#alert-3`). Cả ba có severity, owner và Slack route trong `config/alert_rules.yaml`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4).
- **Khoảng thời gian điều tra:** 2026-09-29 15:55:19–15:55:37 (Asia/Ho_Chi_Minh, lượt challenge đầu); xác minh lại sau fix lúc 17:40:48–17:40:50.
- **Triệu chứng từ metrics:** Lượt đầu có 5/5 HTTP 200; P95 response log 4.485 giây, vượt SLO 3 giây; TTFT P95 50 ms, không có lỗi. Dashboard khi đó hiển thị P95 4.199 giây, P99 4.485 giây và 25 request; client load test ban đầu đo khoảng 17.27 giây do queue. Ở lượt xác minh sau fix, 5/5 vẫn HTTP 200; P95 response log là 2.665 giây, TTFT P95 50 ms, dưới SLO; retrieval span vẫn mất khoảng 2.5 giây.
- **Log line và correlation ID liên quan:** Lượt đầu: `2026-09-29T08:55:23.938507Z response_sent correlation_id=req-98f01a4d latency_ms=4485 ttft_ms=50 tool_name=retrieval tool_success=true`. Xác minh sau fix: `2026-09-29T10:40:50.869916Z response_sent correlation_id=req-a93c886e latency_ms=2665 ttft_ms=50 tool_name=retrieval tool_success=true`.
- **Trace ID và span gây ảnh hưởng:** Lượt đầu: trace `bdbc06ac9b8a22aee144a1b91801afc3`, correlation ID `req-98f01a4d`; child `retrieval` (observation `2969c9be2f86bed5`) 2.505 giây, `llm-generation` 0.165 giây. Xác minh sau fix: trace `bb6486dfbeffac1ed1d9f7034545aed2`, correlation ID `req-a93c886e`; child `retrieval` 2.510 giây.
- **Root cause:** Incident `rag_slow` chèn `sleep(2.5)` vào retrieval. Đồng thời, endpoint async gọi `agent.run()` đồng bộ nên chặn event loop và xếp hàng năm request. Span retrieval đo thêm 2.505 giây; vì queue time nằm ngoài phép đo bên trong agent, client thấy khoảng 17.27 giây trong khi metric nội bộ P95 chỉ là 4.485 giây.
- **Fix action:** Chuyển `agent.run()` sang `run_in_threadpool` trong `app/main.py` và tắt incident bằng `scripts/inject_incident.py --disable`. Lượt kiểm tra sau fix trước đó, khi incident còn bật, client latency giảm từ khoảng 17.27 xuống 4.73 giây; sau khi tắt incident, năm request đạt HTTP 200, client latency 1.582–1.587 giây và response log 1.556–1.567 giây. Xác minh CP3 mới với `rag_slow` bật: 5/5 HTTP 200, client latency 2.715–2.718 giây, response log 2.663–2.665 giây (P95 2.665 giây), TTFT 50 ms, retrieval span 2.507–2.511 giây; lượt này không vượt SLO 3 giây. Sau workload đã tắt incident; `/health` xác nhận cả ba incident đều false.
- **Preventive measure:** Giữ alert P95 request latency >3.000 ms/10 phút; bổ sung metric/alert riêng cho thời lượng retrieval span và đo cả latency đầu-cuối tại middleware để phát hiện queue time mà metric agent hiện tại bỏ sót. Runbook cần nối metric → `correlation_id` trong log → retrieval span trong trace.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Chạy `agent.run()` bằng `run_in_threadpool` trong endpoint async để tránh chặn event loop; kiểm tra CP3 với 5 request đồng thời cho kết quả HTTP 200.
- **Một lỗi/blocker đã gặp:** Endpoint cũ của Langfuse dùng để liệt kê trace trả HTTP 410.
- **Cách tìm nguyên nhân và xử lý:** Đọc endpoint thay thế trong phản hồi lỗi, chuyển sang Observations API v2 và ghép span với request bằng `correlation_id`.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metrics báo tail latency vượt ngưỡng; log xác định request bằng `correlation_id`; trace chỉ ra thời gian nằm ở retrieval hay generation.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt label xác định phiên bản đang chạy và hỗ trợ rollback; token/cost theo dõi mức sử dụng generation; SLO đặt ngưỡng latency để nhận diện ảnh hưởng vận hành.
- **Điều quan trọng nhất đã học:** Cần so sánh latency đầu-cuối với thời lượng từng span vì thời gian chờ trong hàng đợi có thể không xuất hiện trong thời lượng agent.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** FakeLLM mô phỏng output, token và cost; một số ảnh Langfuse đã lưu còn hiển thị `scope.attributes.public_key` nên cần che trước khi nộp. Chưa có commit SHA cuối.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
