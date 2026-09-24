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


def generate_quantitative_briefing(stock_summaries: list) -> str:
    """Tạo bản tin phân tích kỹ thuật định lượng dự phòng (khi toàn bộ API AI bên ngoài bị nghẽn mạng)"""
    above_ma20 = [s for s in stock_summaries if "TRÊN" in s.get("trend_ma", "")]
    below_ma20 = [s for s in stock_summaries if "DƯỚI" in s.get("trend_ma", "")]
    strong_vol = [s for s in stock_summaries if float(s.get("vol_status", "0").split("x")[0]) >= 1.1]
    
    sections = []
    sections.append("🎯 *1. NHẬN ĐỊNH TỔNG QUAN THỊ TRƯỜNG:*")
    market_tone = "Tích cực (Kênh tăng duy trì)" if len(above_ma20) >= len(below_ma20) else "Phân hóa & Thận trọng"
    sections.append(f"• Tín hiệu xu hướng: *{market_tone}* với {len(above_ma20)}/{len(stock_summaries)} mã giữ vững trên đường MA20.")
    sections.append(f"• Trạng thái dòng tiền: {'Dòng tiền chủ động gia tăng ở một số mã trụ.' if strong_vol else 'Thanh khoản ở mức cân bằng, dòng tiền thận trọng tích lũy.'}")
    
    sections.append("\n🚀 *2. ĐIỂM NÓNG CỔ PHIẾU DANH MỤC:*")
    for s in stock_summaries:
        ticker = s['ticker']
        p = s['price']
        chg = s['change_pct']
        rsi = s['rsi']
        trend = s['trend_ma']
        vol = s['vol_status']
        icon = "🟢" if chg > 0 else ("🔴" if chg < 0 else "🟡")
        
        if rsi >= 70:
            status_note = "⚠️ Vùng Quá Mua - Hạn chế mua đuổi, canh chốt lời ngắn hạn."
        elif rsi <= 35:
            status_note = "💎 Vùng Quá Bán - Chờ tín hiệu dòng tiền tạo đáy để gom vị thế."
        elif "TRÊN" in trend:
            status_note = "✅ Giữ vững xu hướng Tăng trên MA20 - Nắm giữ vị thế, canh gia tăng."
        else:
            status_note = "⏳ Dưới MA20 - Tích lũy điều chỉnh, kiên nhẫn chờ vượt kháng cự."
            
        sections.append(f"{icon} *{ticker}* ({p:,.0f} đ, {chg:+0.2f}%): RSI={rsi} | {trend} | Vol={vol}\n   ↳ {status_note}")

    sections.append("\n💡 *3. CHIẾN LƯỢC HÀNH ĐỘNG HÔM NAY:*")
    top_picks = [s for s in stock_summaries if "TRÊN" in s['trend_ma'] and 45 <= s['rsi'] <= 68]
    if top_picks:
        pick = top_picks[0]
        buy_range = f"{pick['price'] * 0.985:,.0f} - {pick['price'] * 1.005:,.0f} đ"
        target = f"{pick['price'] * 1.08:,.0f} đ (+8%)"
        stoploss = f"{pick['ma20'] * 0.96:,.0f} đ (-4%)"
        sections.append(f"• *Mã ưu tiên quan sát:* *{pick['ticker']}*")
        sections.append(f"  - Vùng canh mua: `{buy_range}`")
        sections.append(f"  - Giá mục tiêu ngắn hạn: `{target}`")
        sections.append(f"  - Ngưỡng cắt lỗ (Stoploss): `{stoploss}`")
    else:
        sections.append("• Tỷ trọng khuyến nghị: Duy trì 50-70% cổ phiếu, ưu tiên nhóm dẫn dắt.")

    sections.append("\n⚠️ *Ghi chú:* Phân tích định lượng dựa trên mô hình chỉ báo kỹ thuật RSI, MA20, MA50 & Volume Ratio.")
    return "\n".join(sections)


def ask_gemini(stock_summaries: list, api_key: str) -> str:
    """Gửi dữ liệu kỹ thuật vào Gemini AI phân tích chuyên sâu với cơ chế Multi-Model Cascading Fallback"""
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

    candidate_models = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemma-4-26b-a4b-it",
    ]
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1500
        }
    }
    encoded_data = json.dumps(payload).encode('utf-8')
    
    for model_name in candidate_models:
        clean_model = model_name if not model_name.startswith("models/") else model_name.replace("models/", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=encoded_data, headers={'content-type': 'application/json'})
        
        for sub_attempt in range(2):
            try:
                print(f"[*] Đang kết nối AI qua model: {clean_model} (lần {sub_attempt + 1})...")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    res_data = json.loads(resp.read().decode())
                    text_result = res_data['candidates'][0]['content']['parts'][0]['text']
                    if text_result and len(text_result.strip()) > 50:
                        print(f"[+] Model {clean_model} đã phân tích thành công!")
                        return text_result
            except urllib.error.HTTPError as e:
                print(f"[!] Model {clean_model} trả về mã lỗi HTTP {e.code}: {e.reason}")
                if e.code in (503, 429, 404):
                    print(f"    -> Đang tự động chuyển sang model dự phòng kế tiếp...")
                    time.sleep(1)
                    break
                time.sleep(2)
            except Exception as e:
                print(f"[!] Lỗi khi gọi model {clean_model}: {e}")
                time.sleep(1)
                
    print("[!] Các model AI đám mây đang quá tải tạm thời. Kích hoạt bộ phân tích định lượng dự phòng...")
    return generate_quantitative_briefing(stock_summaries)


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
