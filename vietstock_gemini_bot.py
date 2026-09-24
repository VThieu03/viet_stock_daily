import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

# ================= ĐỌC CẤU HÌNH TỪ .ENV HOẶC ENVIRONMENT =================
def get_env_var(key, default=""):
    val = os.environ.get(key)
    if val:
        return val
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default

TELEGRAM_BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = get_env_var("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = get_env_var("GEMINI_API_KEY", "")

# Danh mục cổ phiếu Việt Nam theo dõi
WATCHLIST = ["FPT", "HPG", "VCB", "SSI", "MWG", "TCB", "VHM"]
# ==========================================================================


def fetch_stock_data(ticker: str):
    """Lấy dữ liệu giá và khối lượng lịch sử qua Yahoo Finance"""
    symbol = f"{ticker}.VN"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode())
            quote = res['chart']['result'][0]['indicators']['quote'][0]
            
            closes = [c for c in quote['close'] if c is not None]
            volumes = [v for v in quote['volume'] if v is not None]
            
            if len(closes) < 20:
                return None
            
            latest_price = closes[-1]
            prev_price = closes[-2]
            pct_change = ((latest_price - prev_price) / prev_price) * 100
            
            # Tính đường trung bình MA20, MA50
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
            
            # Tính chỉ số sức mạnh tương đối RSI (14 phiên)
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas[-14:]]
            losses = [-d if d < 0 else 0 for d in deltas[-14:]]
            avg_gain = sum(gains) / 14 if sum(gains) > 0 else 0.001
            avg_loss = sum(losses) / 14 if sum(losses) > 0 else 0.001
            rs = avg_gain / avg_loss
            rsi_14 = 100 - (100 / (1 + rs))
            
            # Khối lượng so với trung bình 20 phiên
            latest_vol = volumes[-1]
            avg_vol_20 = sum(volumes[-20:]) / 20
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
            
            return {
                "ticker": ticker,
                "price": latest_price,
                "change_pct": round(pct_change, 2),
                "rsi": round(rsi_14, 1),
                "ma20": round(ma20, 1),
                "ma50": round(ma50, 1),
                "trend_ma": "TRÊN MA20" if latest_price >= ma20 else "DƯỚI MA20",
                "vol_status": f"{vol_ratio:.1f}x TB20P"
            }
    except Exception as e:
        print(f"[!] Lỗi khi lấy mã {ticker}: {e}")
        return None


def ask_gemini(stock_summaries: list, api_key: str) -> str:
    """Gửi dữ liệu kỹ thuật vào Gemini Pro / Flash để phân tích chuyên sâu với retry tự động"""
    data_text = "\n".join([
        f"- Mã {s['ticker']}: Giá {s['price']:,.0f} VND ({s['change_pct']:+0.2f}%), "
        f"RSI={s['rsi']}, Vị thế: {s['trend_ma']}, Khối lượng={s['vol_status']}"
        for s in stock_summaries
    ])
    
    prompt = f"""Bạn là Giám đốc Khối Phân tích Chiến lược Chứng khoán Việt Nam (Senior Equity Research Analyst). 
Dưới đây là bảng số liệu kỹ thuật phiên gần nhất của danh mục theo dõi:

{data_text}

Hãy soạn một BẢN TIN PHÂN TÍCH BUỔI SÁNG gửi nhà đầu tư qua Telegram với phong cách chuyên nghiệp, dứt khoát, sắc bén:
1. 🎯 NHẬN ĐỊNH TỔNG QUAN: Xu hướng thị trường và dòng tiền các nhóm ngành trụ cột (Ngân hàng, Thép, Bán lẻ, Công nghệ, Bất động sản).
2. 🚀 ĐIỂM NÓNG CỔ PHIẾU: 
   - Mã nào đang có dòng tiền vào mạnh, giữ vững kênh tăng hoặc có tín hiệu tích lũy cạn kiệt chuẩn bị bùng nổ?
   - Mã nào chạm vùng Quá Mua (RSI > 70) hoặc gãy MA20 cần quản trị rủi ro?
3. 💡 CHIẾN LƯỢC HÀNH ĐỘNG HÔM NAY:
   - Gợi ý cụ thể: Mã mua tiềm năng, vùng giá canh mua, giá mục tiêu chốt lời ngắn hạn và ngưỡng cắt lỗ (Stoploss).

Yêu cầu định dạng: Ngắn gọn, có gạch đầu dòng, icon emoji nổi bật, dễ đọc nhanh trên điện thoại."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1500
        }
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'content-type': 'application/json'}
    )
    
    # Retry tối đa 4 lần nếu gặp quá tải tức thời
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_data = json.loads(resp.read().decode())
                return res_data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            print(f"[!] Lần thử {attempt+1} gặp lỗi: {e}. Đang thử lại sau 2 giây...")
            time.sleep(2)

    return "⚠️ Hiện tại dịch vụ phân tích AI đang bảo trì. Vui lòng thử lại sau ít phút."


def send_telegram(message: str, bot_token: str, chat_id: str):
    """Bắn báo cáo hoàn chỉnh về Telegram cá nhân"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    full_message = f"☕ *BẢN TIN PHÂN TÍCH CHỨNG KHOÁN SÁNG {today_str}*\n_Phân tích tự động bởi Gemini AI_\n\n{message}"
    
    # Chia nhỏ tin nhắn nếu dài hơn giới hạn 4096 ký tự của Telegram
    max_len = 3800
    parts = [full_message[i:i+max_len] for i in range(0, len(full_message), max_len)]
    
    for part in parts:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "Markdown"
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'content-type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                print("[+] Đã gửi thành công về Telegram của bạn!")
        except urllib.error.HTTPError as e:
            # Fallback gửi không dùng Markdown nếu lỗi cú pháp tag
            payload.pop("parse_mode", None)
            req2 = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'content-type': 'application/json'})
            with urllib.request.urlopen(req2, timeout=10):
                print("[+] Đã gửi thành công về Telegram (Plaintext)!")


def run_pipeline():
    print("[*] Đang thu thập số liệu danh mục cổ phiếu Việt Nam (FPT, HPG, VCB, SSI, MWG, TCB, VHM)...")
    summaries = []
    for ticker in WATCHLIST:
        data = fetch_stock_data(ticker)
        if data:
            summaries.append(data)
            print(f"    -> Đã lấy xong: {ticker:4s} (Giá: {data['price']:>8,.0f} đ | RSI: {data['rsi']:4.1f} | {data['trend_ma']} | Vol: {data['vol_status']})")
            
    if not summaries:
        print("[!] Không lấy được dữ liệu cổ phiếu nào.")
        return
        
    print("\n[*] Đang gửi dữ liệu cho Gemini AI phân tích chiến lược...")
    if not GEMINI_API_KEY:
        print("[!] Chưa cấu hình GEMINI_API_KEY trong file .env hoặc biến môi trường.")
        return
        
    analysis = ask_gemini(summaries, GEMINI_API_KEY)
    
    print("\n[*] Đang bắn bản tin phân tích về Telegram cá nhân...")
    send_telegram(analysis, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    print("\n🎉 HOÀN TẤT TOÀN BỘ QUY TRÌNH!")


if __name__ == "__main__":
    run_pipeline()
