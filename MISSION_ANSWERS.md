# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. **Hardcoded API key và Database credentials:** Trong `develop/app.py` có chứa `OPENAI_API_KEY` và `DATABASE_URL` trực tiếp trong mã nguồn. Điều này vi phạm nghiêm trọng nguyên tắc bảo mật và nguyên tắc "Config" của 12-Factor App. Nếu đẩy code lên GitHub, các khóa này sẽ bị lộ.
2. **Lưu cấu hình cứng trong code (Hardcoded Config):** Các tham số như `DEBUG = True` và `MAX_TOKENS = 500` được đặt trực tiếp trong file code, gây khó khăn khi cần thay đổi giữa các môi trường khác nhau (dev, staging, production).
3. **Sử dụng `print()` thay vì Structured Logging:** Việc in log bằng hàm `print()` không ghi nhận thời gian, cấp độ lỗi (severity level), và nghiêm trọng hơn là in thẳng khóa bảo mật ra log (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`). Trong production, cần dùng structured logging (ví dụ JSON format) để log aggregator dễ parse và lưu trữ an toàn.
4. **Không có Health Check endpoint:** Không có các route `/health` hay `/ready`. Nếu ứng dụng bị treo hoặc crash, các nền tảng đám mây (như Railway, Render, K8s) sẽ không phát hiện ra để tự động khởi động lại container hoặc ngừng hướng traffic tới nó.
5. **Hardcode Host và Port:** Ứng dụng binding trực tiếp vào `localhost` và cố định `port=8000`. Khi chạy trong Docker hoặc deploy lên cloud, ta cần bind sang `0.0.0.0` để bên ngoài có thể truy cập được, và port phải lấy động từ biến môi trường `PORT` do nền tảng tự động inject vào. Chạy `reload=True` trong production cũng gây lãng phí tài nguyên và rủi ro bảo mật.

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| **Config** | Hardcode trong file code | Load từ Environment Variables qua config module | Dễ dàng thay đổi cấu hình ứng dụng giữa các môi trường mà không cần sửa code; bảo mật secrets không bị lộ. |
| **Health Check** | Không có | Có `/health` (Liveness) và `/ready` (Readiness) | Giúp orchestrator (Docker/K8s/Cloud) giám sát trạng thái ứng dụng, tự động restart nếu lỗi và định tuyến traffic chính xác. |
| **Logging** | Dùng hàm `print()`, log cả thông tin nhạy cảm | JSON structured logging, không log secrets | Giúp lưu trữ tập trung, dễ tìm kiếm, phân tích lỗi tự động bằng các công cụ log aggregator mà vẫn bảo mật thông tin. |
| **Shutdown** | Tắt đột ngột (Hard termination) | Graceful shutdown (xử lý tín hiệu `SIGTERM`) | Đảm bảo hoàn thành các request đang xử lý dở dang và giải phóng tài nguyên (database, redis connections) trước khi container dừng hẳn. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:** `python:3.11` (Full Debian-based Python image, kích thước lớn ~1GB).
2. **Working directory:** `/app` (thư mục làm việc mặc định trong container).
3. **Tại sao COPY requirements.txt trước?** Để tận dụng cơ chế Docker Layer Caching. Nếu danh sách thư viện không thay đổi, Docker sẽ bỏ qua bước cài đặt (`pip install`) vốn mất nhiều thời gian, giúp tăng tốc độ build các lần sau.
4. **CMD vs ENTRYPOINT khác nhau thế nào?** 
   - `ENTRYPOINT` định nghĩa câu lệnh cố định được chạy khi container start.
   - `CMD` định nghĩa các tham số mặc định cho câu lệnh đó. `CMD` có thể dễ dàng bị ghi đè khi chạy lệnh `docker run <image> <new_cmd>`, còn `ENTRYPOINT` thì không bị ghi đè trực tiếp mà cần cờ `--entrypoint`.

### Exercise 2.3: Image size comparison
- Develop: 1660 MB
- Production: 247 MB
- Difference: 85.1% (85.1% reduction in size)

### Exercise 2.4: Architecture diagram
Sơ đồ kiến trúc của hệ thống load balancer được định nghĩa trong `docker-compose.yml`:
```
Client (Port 80)
   │
   ▼
[Nginx (Load Balancer)] (Phân phối traffic sang các instance)
   │
   ├───► [Agent Instance 1] (Port 8000) ───┐
   ├───► [Agent Instance 2] (Port 8000) ───┼──► [Redis] (Port 6379) (Stateless Session)
   └───► [Agent Instance 3] (Port 8000) ───┘
```
**Cách các services giao tiếp:**
- **Nginx** lắng nghe ở port `80` bên ngoài, định tuyến (reverse proxy) các request đến 3 instance của service **agent** (sử dụng thuật toán round-robin mặc định).
- Cả 3 instance của **agent** đều cấu hình `REDIS_URL` để lưu trữ/đọc session và conversation history từ một service **redis** duy nhất ở port `6379`. Nhờ đó, dù request của một user bị gửi đến bất kỳ instance nào, trạng thái hội thoại vẫn được đồng bộ và nhất quán (Stateless).

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: https://day12-agent-deployment-production.up.railway.app
- Screenshot: [Deployment Dashboard](screenshots/dashboard.png)

### Exercise 3.2: Render vs Railway configuration comparison
So sánh cấu hình `render.yaml` và `railway.toml`:
1. **Mục đích sử dụng:**
   - `render.yaml` là file cấu hình dạng Infrastructure-as-Code (Blueprint) để khai báo toàn bộ tài nguyên trên Render (bao gồm Web Service, Redis, Database, và các biến môi trường đi kèm).
   - `railway.toml` chỉ tập trung cấu hình cách build và deploy cho duy nhất 1 service cụ thể của Railway.
2. **Khai báo đa dịch vụ (Multi-service orchestration):**
   - `render.yaml` cho phép khai báo nhiều dịch vụ đồng thời (như khai báo service `ai-agent` dạng web và service `agent-cache` dạng redis) và tự động liên kết chúng.
   - `railway.toml` không hỗ trợ khai báo đa dịch vụ; việc tạo Redis hay liên kết dịch vụ trên Railway được thiết lập trực tiếp qua Dashboard hoặc Railway CLI.
3. **Cơ chế Build:**
   - `railway.toml` khai báo builder (ví dụ: `builder = "NIXPACKS"` hoặc `DOCKER`), Railway tự động nhận diện Dockerfile.
   - `render.yaml` sử dụng `buildCommand` (ví dụ: `pip install -r requirements.txt`) và `runtime: python` nếu chạy dạng Native Python, hoặc tự động build nếu phát hiện Dockerfile.
4. **Quản lý biến môi trường (Secrets):**
   - `render.yaml` hỗ trợ các thuộc tính bảo mật nâng cao như `generateValue: true` (Render tự sinh giá trị ngẫu nhiên) hoặc `sync: false` (yêu cầu người dùng điền thủ công trên UI).
   - `railway.toml` không lưu trữ biến môi trường trong file cấu hình để tránh lộ lọt thông tin; biến môi trường được quản lý hoàn toàn ở Dashboard/CLI của Railway.

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results
Dưới đây là kết quả kiểm tra cục bộ các tính năng bảo mật bảo vệ API:

#### 1. Yêu cầu API Key (Authentication)
Khi gọi API `/ask` không có header `X-API-Key`:
```json
{
  "detail": "Invalid or missing API key. Include header: X-API-Key: <key>"
}
```
Response status: `401 Unauthorized`.

Khi có header `X-API-Key` hợp lệ:
```json
{
  "question": "Hello",
  "answer": "Mock LLM Response: Hello",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T08:12:00.000Z"
}
```
Response status: `200 OK`.

#### 2. Rate Limiting (Sliding Window)
Khi thực hiện gọi liên tục vượt quá giới hạn (10 req/phút):
```json
{
  "detail": "Rate limit exceeded: 20 req/min"
}
```
Response status: `429 Too Many Requests` với header `Retry-After: 60`.

### Exercise 4.4: Cost Guard implementation
**Phương pháp thiết kế:**
- Cost guard hoạt động bằng cách giám sát số lượng token đầu vào (input tokens) và đầu ra (output tokens) của mỗi request.
- Chi phí ước tính được tính toán dựa trên bảng giá định trước của model sử dụng (ví dụ GPT-4o-mini: $0.15/1M input tokens, $0.60/1M output tokens).
- Trước khi gọi LLM, ta thực hiện `check_budget()` để xác nhận tổng chi phí đã tiêu thụ của người dùng trong ngày/tháng chưa vượt quá ngân sách tối đa cấu hình (`DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD`).
- Nếu vượt quá ngân sách, API sẽ trả về lỗi `503 Service Unavailable` hoặc `402 Payment Required`, từ chối tiếp tục phục vụ để tránh phát sinh chi phí ngoài dự kiến.
- Sau khi nhận phản hồi từ LLM, ta ghi nhận lượng token thực tế đã tiêu thụ và cộng dồn vào storage (như Redis).

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
1. **Health Check & Readiness Probes:**
   - Endpoint `/health` (Liveness probe) trả về `200 OK` nhanh chóng để thông báo container vẫn đang sống.
   - Endpoint `/ready` (Readiness probe) kiểm tra kết kết nối tới các service phụ thuộc như Redis và database. Nếu kết nối thành công trả về `200 OK`, nếu lỗi trả về `503 Service Unavailable` để load balancer tạm thời không chuyển traffic đến instance này.
2. **Graceful Shutdown:**
   - Ứng dụng lắng nghe tín hiệu `SIGTERM` (được gửi bởi docker daemon hoặc K8s khi muốn tắt container).
   - Khi nhận tín hiệu, ứng dụng chuyển trạng thái `is_ready = False` (để Readiness probe trả về 503, load balancer gỡ instance khỏi danh sách hoạt động), hoàn thành các request đang xử lý dở và đóng các kết nối an toàn trước khi thoát.
3. **Stateless Session Design:**
   - Để ứng dụng có thể scale-out ra nhiều bản sao (replica) chạy song song đằng sau load balancer, ta lưu trữ lịch sử cuộc hội thoại (conversation history) trong Redis thay vì lưu trong RAM của instance.
   - Bất kỳ instance nào khi nhận được request từ người dùng đều có thể đọc/ghi session từ Redis thông qua `session_id`, giải quyết triệt để lỗi mất hội thoại khi request bị định tuyến sang một instance khác.
