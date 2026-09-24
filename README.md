# 📈 VietStock Daily: AI-Powered Institutional Stock Analysis via Telegram

Hệ thống tự động hóa phân tích thị trường chứng khoán Việt Nam chuẩn chuyên gia & định chế tài chính mỗi buổi sáng, ứng dụng **Google Gemini AI (Persona Giám đốc Khối Phân tích Chiến lược & Quản lý Quỹ)** và tự động gửi báo cáo trực tiếp về **Telegram cá nhân**.

---

## 🌟 Nâng Cấp Toàn Diện Chuẩn Chuyên Gia (Institutional Grade)

1. **Bối cảnh Vĩ mô & Liên thị trường (Intermarket Pulse):**
   - Theo dõi tự động đêm qua từ Phố Wall: **Dow Jones (`^DJI`)**, Chỉ số **DXY (`DX-Y.NYB`)** đo áp lực tỷ giá & dòng vốn ngoại, **Giá Dầu WTI (`CL=F`)**, và **Giá Vàng thế giới (`GC=F`)**.
   - Cập nhật điểm tin tài chính - chứng khoán chọn lọc sáng sớm từ **CafeF RSS**.

2. **Chỉ số thị trường chung VN-INDEX (Market Regime & Breadth):**
   - Phân tích điểm số, biến động, tỷ lệ thanh khoản so với TB20 phiên, vị thế MA20/MA50, RSI-14 và các ngưỡng Hỗ trợ / Kháng cự kỹ thuật then chốt của chỉ số VN-Index.

3. **Bộ Chỉ Báo Kỹ Thuật Đa Chiều Chuẩn CMT (Chartered Market Technician):**
   - **Xung lượng (Momentum):** MACD (12, 26, 9), Đường Signal, Histogram để nhận diện điểm giao cắt sớm (Golden/Death Cross).
   - **Độ biến động (Volatility):** Dải Bollinger Bands (20, 2) và trạng thái thắt nút cổ chai (Bandwidth Squeeze < 7.5%) để đón đầu sóng bùng nổ biến động.
   - **Hành động giá (Price Action):** Nhận diện nến rút chân bắt đáy (Pinbar/Hammer), nến cụt đầu bị bán ngược (Shooting Star), nến Marubozu đặc hay giằng co Doji.
   - **Kháng cự / Hỗ trợ Kỹ thuật Thực tế:** Đỉnh/đáy 20 phiên (Swing High/Low) phục vụ tính toán điểm Mua, Target và Stoploss thực chiến.

4. **Bản đồ Phân hóa Dòng tiền theo Nhóm Ngành (Sector Rotation):**
   - Tự động gom nhóm: Công nghệ, Ngân hàng, Thép, Chứng khoán, Bán lẻ, Bất động sản, Dầu khí... để tìm ra nhóm ngành dẫn dắt (Leading Sector).
   - Cho phép tùy biến danh mục theo dõi linh hoạt qua biến `WATCHLIST` trong `.env`.

5. **Đa luồng Siêu tốc & Độ Tin Cậy Tuyệt Đối (High Reliability):**
   - Sử dụng `ThreadPoolExecutor` (chuẩn Python Standard Library) để quét và phân tích kỹ thuật toàn bộ danh mục song song trong chưa đầy 1 giây.
   - **Cascading Model Fallback:** Tự động chuyển đổi chuỗi model Gemini khi bị lỗi 503/429.
   - **Heuristic Engine Chuyên sâu:** Tự động phát hành bản tin định lượng 5 phần chuẩn mực nếu toàn bộ AI API ngắt kết nối.
   - **Telegram Smart Delivery:** Tự động chia nhỏ tin nhắn an toàn `< 3800` ký tự và hỗ trợ chế độ Fallback Plaintext chống lỗi cú pháp.

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Kích hoạt Bot trên Telegram
1. Mở Telegram, tìm bot: **`@Vietstock_claude_bot`**
2. Nhấn nút **START** (hoặc gửi `/start`) để cấp quyền nhận tin nhắn.

### 2. Chạy thủ công trên máy tính
- **Cách 1:** Nhấp đúp vào file `run_stock_daily.bat` (hoặc phím tắt ngoài Desktop `Chay_Bot_Chung_Khoan.bat`).
- **Cách 2:** Mở Terminal tại thư mục dự án và chạy:
  ```bash
  python vietstock_gemini_bot.py
  ```

---

## ⚙️ Cấu Hình Tự Động Hóa Cloud (GitHub Actions)

Quy trình tự động hóa được định nghĩa tại `.github/workflows/morning_stock.yml`:
- Tự động kích hoạt lúc **01:00 UTC (08:00 Sáng giờ Việt Nam)** các ngày giao dịch từ Thứ 2 đến Thứ 6.
- Sử dụng các biến bí mật (GitHub Secrets):
  * `TELEGRAM_BOT_TOKEN`
  * `TELEGRAM_CHAT_ID`
  * `GEMINI_API_KEY`
