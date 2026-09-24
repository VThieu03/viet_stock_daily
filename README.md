# 📈 VietStock Daily: AI-Powered Automated Stock Analysis via Telegram

Hệ thống tự động hóa phân tích thị trường chứng khoán Việt Nam mỗi buổi sáng ứng dụng **Google Gemini AI** và bắn báo cáo trực tiếp về **Telegram Bot**.

---

## 🌟 Tính Năng Chính

- **Thu thập dữ liệu giá & khối lượng thời gian thực:**
  - Tự động lấy dữ liệu lịch sử các mã cổ phiếu hàng đầu thị trường (VN30, FPT, HPG, VCB, SSI, MWG, TCB, VHM...).
- **Tính toán chỉ báo kỹ thuật cốt lõi:**
  - **RSI (14 phiên):** Phát hiện trạng thái Quá Mua (Overbought > 70) và Quá Bán (Oversold < 30).
  - **Đường xu hướng MA20, MA50:** Xác định vị thế xu hướng tăng/giảm ngắn và trung hạn.
  - **Tỷ lệ khối lượng (Volume Ratio):** Nhận diện phiên bùng nổ thanh khoản so với trung bình 20 phiên.
- **Phân tích chiến lược chuyên sâu bởi Gemini AI:**
  - Nhận định xu hướng dòng tiền ngành dẫn dắt (Ngân hàng, Thép, Bán lẻ, Công nghệ, BĐS).
  - Bóc tách điểm nóng cổ phiếu: Điểm Breakout, dòng tiền tổ chức, vùng cảnh báo gãy nền.
  - Khuyến nghị hành động cụ thể: Vùng giá canh mua, giá mục tiêu chốt lời và ngưỡng cắt lỗ (Stoploss).
- **Tự động hóa hoàn toàn 100% (08:00 AM mỗi sáng):**
  - Tích hợp **GitHub Actions** chạy ngầm 0 đồng trên Cloud từ Thứ 2 đến Thứ 6.
  - Hỗ trợ chạy nội bộ qua **Windows Task Scheduler**.

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Kích hoạt Bot trên Telegram
1. Mở Telegram, tìm bot: **`@Vietstock_claude_bot`**
2. Nhấn nút **START** (hoặc gửi `/start`) để cấp quyền nhận tin nhắn.

### 2. Chạy thủ công trên máy tính
- **Cách 1:** Nhấp đúp vào file `run_stock_daily.bat` (hoặc file ngoài Desktop `Chay_Bot_Chung_Khoan.bat`).
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
