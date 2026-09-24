import os
import json
import time
import math
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

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

# Danh mục theo dõi tùy biến qua .env
ENV_WATCHLIST = get_env_var("WATCHLIST", "")
if ENV_WATCHLIST:
    WATCHLIST = [s.strip().upper() for s in ENV_WATCHLIST.split(",") if s.strip()]
else:
    WATCHLIST = ["FPT", "HPG", "VCB", "SSI", "MWG", "TCB", "VHM", "MBB"]

SECTOR_MAP = {
    "FPT": "Công nghệ", "MWG": "Bán lẻ", "FRT": "Bán lẻ", "DGC": "Hóa chất",
    "VCB": "Ngân hàng", "TCB": "Ngân hàng", "MBB": "Ngân hàng", "CTG": "Ngân hàng", "STB": "Ngân hàng",
    "SSI": "Chứng khoán", "VND": "Chứng khoán", "VCI": "Chứng khoán",
    "HPG": "Thép", "HSG": "Thép", "NKG": "Thép",
    "VHM": "BĐS", "VIC": "BĐS", "DIG": "BĐS", "PDR": "BĐS",
    "PVS": "Dầu khí", "PVD": "Dầu khí", "BSR": "Dầu khí"
}
# ==========================================================================


def calc_ema(prices: list, period: int) -> list:
    if len(prices) < period:
        return prices
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append((p - ema[-1]) * multiplier + ema[-1])
    return ema


# ================= 1. THU THẬP VĨ MÔ & LIÊN THỊ TRƯỜNG =================
def fetch_intermarket_pulse() -> dict:
    tickers = {"Dow Jones": "^DJI", "DXY": "DX-Y.NYB", "Dầu WTI": "CL=F"}
    results = {}
    for name, sym in tickers.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d&range=5d"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                closes = [c for c in data['chart']['result'][0]['indicators']['quote'][0]['close'] if c is not None]
                if len(closes) >= 2:
                    pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                    results[name] = {"price": round(closes[-1], 2), "pct": round(pct, 2)}
        except Exception:
            pass
    return results


def fetch_macro_news() -> list:
    url = "https://cafef.vn/thi-truong-chung-khoan.rss"
    headlines = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            root = ET.fromstring(resp.read())
            items = root.findall('.//item')
            for item in items[:2]:
                title_elem = item.find('title')
                if title_elem is not None and title_elem.text:
                    clean_title = title_elem.text.strip().replace("\n", " ")
                    headlines.append(clean_title)
    except Exception:
        pass
    return headlines


# ================= 2. THU THẬP CHỈ SỐ VN-INDEX =================
def fetch_vnindex_summary() -> dict:
    try:
        now = int(time.time())
        from_time = now - 120 * 86400
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from={from_time}&to={now}&symbol=VNINDEX&resolution=1D"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            closes = [c for c in data.get('c', []) if c is not None]
            volumes = [v for v in data.get('v', []) if v is not None]
            lows = [l for l in data.get('l', []) if l is not None]
            highs = [h for h in data.get('h', []) if h is not None]

            if len(closes) >= 20:
                latest = closes[-1]
                prev = closes[-2]
                pct = ((latest - prev) / prev) * 100
                ma20 = sum(closes[-20:]) / 20
                ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
                avg_vol20 = sum(volumes[-20:]) / 20
                vol_ratio = volumes[-1] / avg_vol20 if avg_vol20 > 0 else 1.0

                return {
                    "close": round(latest, 2),
                    "change_pct": round(pct, 2),
                    "ma20": round(ma20, 2),
                    "ma50": round(ma50, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "support": round(min(lows[-20:]), 0),
                    "resistance": round(max(highs[-20:]), 0),
                    "trend": "Đang chỉnh dưới MA20" if latest < ma20 else "Ổn định trên MA20"
                }
    except Exception:
        pass
    return None


# ================= 3. PHÂN TÍCH KỸ THUẬT DANH MỤC CỔ PHIẾU =================
def fetch_stock_data_pro(ticker: str) -> dict:
    symbol = f"{ticker}.VN"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            res = json.loads(response.read().decode())
            quote = res['chart']['result'][0]['indicators']['quote'][0]
            
            closes = [c for c in quote.get('close', []) if c is not None]
            opens = [o for o in quote.get('open', []) if o is not None]
            highs = [h for h in quote.get('high', []) if h is not None]
            lows = [l for l in quote.get('low', []) if l is not None]
            volumes = [v for v in quote.get('volume', []) if v is not None]
            
            if len(closes) < 30:
                return None
            
            latest_price = closes[-1]
            prev_price = closes[-2]
            pct_change = ((latest_price - prev_price) / prev_price) * 100
            
            ma20 = sum(closes[-20:]) / 20
            
            # RSI 14
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas[-14:]]
            losses = [-d if d < 0 else 0 for d in deltas[-14:]]
            avg_gain = sum(gains) / 14 if sum(gains) > 0 else 0.001
            avg_loss = sum(losses) / 14 if sum(losses) > 0 else 0.001
            rsi = 100 - (100 / (1 + (avg_gain / avg_loss)))
            
            # MACD
            ema12 = calc_ema(closes, 12)
            ema26 = calc_ema(closes, 26)
            macd_series = [e12 - e26 for e12, e26 in zip(ema12[26-12:], ema26)]
            signal_series = calc_ema(macd_series, 9)
            hist = macd_series[-1] - signal_series[-1]
            prev_hist = macd_series[-2] - signal_series[-2] if len(macd_series) >= 2 else hist
            macd_buy = hist > 0 and prev_hist <= 0
            
            # Bollinger Bands Squeeze
            subset20 = closes[-20:]
            std_dev = math.sqrt(sum((x - ma20)**2 for x in subset20) / 20)
            bandwidth = ((4 * std_dev) / ma20) * 100
            is_squeeze = bandwidth < 7.5
            
            # Candlestick
            o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
            body = abs(c - o)
            is_hammer = (min(o, c) - l) >= 1.8 * body and body > 0
            
            vol_ratio = volumes[-1] / (sum(volumes[-20:]) / 20) if volumes else 1.0

            return {
                "ticker": ticker,
                "price": latest_price,
                "change_pct": round(pct_change, 2),
                "rsi": round(rsi, 1),
                "ma20": round(ma20, 0),
                "support": round(min(lows[-20:]), 0),
                "resistance": round(max(highs[-20:]), 0),
                "is_squeeze": is_squeeze,
                "vol_ratio": round(vol_ratio, 1),
                "macd_buy": macd_buy,
                "is_hammer": is_hammer
            }
    except Exception:
        return None


# ================= 4. BỘ THAM MƯU DUYỆT LỆNH DỰ PHÒNG =================
def generate_action_orders_fallback(stock_summaries: list, vnindex: dict, intermarket: dict, news: list) -> str:
    """Tạo bảng kế hoạch duyệt lệnh thực chiến dự phòng (< 900 ký tự) khi AI ngắt kết nối"""
    lines = []
    lines.append("☕ SẾP DUYỆT NHANH KẾ HOẠCH PHIÊN HÔM NAY:\n")
    
    # 1. Đánh giá 1 câu
    lines.append("⚠️ 1. ĐÁNH GIÁ 1 CÂU:")
    if vnindex and vnindex.get("change_pct", 0) < 0:
        lines.append(f"Thị trường ĐANG CHỈNH ({vnindex['close']:,.0f} đ, {vnindex['change_pct']:+.1f}%); chiến lược ưu tiên PHÒNG THỦ, tuyệt đối KHÔNG mua đuổi ATO.")
    else:
        lines.append("Thị trường ĐANG TÍCH LŨY PHÂN HÓA; ưu tiên lọc mã có dòng tiền riêng, chỉ giải ngân từng phần.")
        
    # 2. Các lệnh chờ sếp duyệt
    lines.append("\n📋 2. CÁC LỆNH CHỜ SẾP DUYỆT SÁNG NAY:")
    
    # Tìm mã khỏe nhất (xung lực tốt, vol lớn)
    bulls = [s for s in stock_summaries if s.get("change_pct", 0) > 0 or s.get("vol_ratio", 1.0) >= 1.2]
    top_buy = bulls[0] if bulls else stock_summaries[0]
    buy_price = round(top_buy['price'] * 0.985, -2)
    tp_price = round(top_buy['resistance'], -2) if top_buy['resistance'] > top_buy['price'] else round(top_buy['price'] * 1.08, -2)
    sl_price = round(top_buy['support'] * 0.98, -2)
    lines.append(f"• [MUA RÌNH RẬP] {top_buy['ticker']}: Kê mua giá `{buy_price:,.0f} đ` (20% NAV) | Mục tiêu: `{tp_price:,.0f} đ` | Cắt lỗ gãy `{sl_price:,.0f} đ`. Lý do: Tiền lớn đỡ giá tích cực.")

    # Tìm mã yếu nhất
    bears = [s for s in stock_summaries if s.get("change_pct", 0) < -1.0 or s.get("rsi", 50) < 35]
    if bears:
        top_sell = bears[0]
        sell_price = round(top_sell['price'] * 1.015, -2)
        lines.append(f"• [BÁN / HẠ TỶ TRỌNG] {top_sell['ticker']}: Hồi lên vùng `{sell_price:,.0f} đ` là sút 50% vị thế, không trung bình giá. Lý do: Áp lực bán lớn, rủi ro thủng đáy.")

    # Tìm mã siết nền
    squeezes = [s for s in stock_summaries if s.get("is_squeeze") or abs(s.get("change_pct", 0)) < 0.6]
    candidate_sq = [s for s in squeezes if s['ticker'] != top_buy['ticker'] and (not bears or s['ticker'] != bears[0]['ticker'])]
    if candidate_sq:
        sq = candidate_sq[0]
        lines.append(f"• [CHỜ NỔ VOL] {sq['ticker']}: Kê gom nhẹ vùng `{sq['price']:,.0f} đ` (15% NAV), chỉ gia tăng khi bứt phá dứt khoát `{sq['resistance']:,.0f} đ`. Lý do: Tích lũy siết nền cạn vol.")

    # 3. Mốc báo động đỏ
    lines.append("\n🚨 3. MỐC BÁO ĐỘNG ĐỎ CỦA PHIÊN:")
    v_sup = vnindex.get('support', 1770) if vnindex else 1770
    lines.append(f"• Kịch bản sập: Nếu trước 10:30 VN-Index thủng mốc `{v_sup:,.0f} đ` -> Khóa mua toàn danh mục, hạ margin về 0.")
    lines.append("• Kịch bản ổn định: VN-Index rút chân giữ vững hỗ trợ, tiếp tục nắm giữ vị thế hiện tại.")

    return "\n".join(lines)


# ================= 5. AI CHIEF OF STAFF: SOẠN BẢNG LỆNH HÀNH ĐỘNG DỨT KHOÁT =================
def ask_gemini_action_orders(stock_summaries: list, vnindex: dict, intermarket: dict, news: list, api_key: str) -> str:
    """Đóng vai Trưởng ban Tham mưu Đầu tư (Chief of Staff): Soạn LỆNH CỤ THỂ để Sếp chỉ cần DUYỆT"""
    inter_str = ", ".join([f"{k}: {v['price']:,.1f} ({v['pct']:+0.2f}%)" for k, v in intermarket.items()]) if intermarket else "Ổn định"
    news_str = news[0] if news else "Khối ngoại đang tái cơ cấu"
    vni_str = f"{vnindex['close']:,.2f} đ ({vnindex['change_pct']:+0.2f}%), {vnindex['trend']}, Hỗ trợ MA50={vnindex['ma50']:,.0f}, Đáy={vnindex['support']:,.0f}, Cản={vnindex['resistance']:,.0f}" if vnindex else "Tích lũy"

    stocks_text = "\n".join([
        f"- {s['ticker']}: Giá {s['price']:,.0f} đ ({s['change_pct']:+0.1f}%), RSI={s['rsi']}, Vol={s['vol_ratio']}x, Hỗ trợ={s['support']:,.0f}, Cản={s['resistance']:,.0f}, "
        f"{'Siết nền nén nổ' if s['is_squeeze'] else ''}{', MACD báo MUA' if s['macd_buy'] else ''}{', Nến rút chân' if s['is_hammer'] else ''}"
        for s in stock_summaries
    ])

    prompt = f"""Bạn là Trưởng ban Tham mưu Đầu tư (Chief of Staff) kiêm Thư ký chiến lược riêng của Giám đốc (Sếp).
Sếp chỉ có đúng 15 giây trước phiên ATO để DUYỆT LỆNH. Sếp KHÔNG cần nghe lý thuyết kỹ thuật RSI/MACD, Sếp CỰC GHÉT nói nước đôi kiểu "nếu tăng thì... nếu giảm thì...".
Nhiệm vụ: Soạn KẾ HOẠCH HÀNH ĐỘNG DỨT KHOÁT ĐẦU NGÀY. Mọi mã đều phải có GIÁ CỤ THỂ và HÀNH ĐỘNG RÕ RÀNG để Sếp ném cho broker vào lệnh.

DỮ LIỆU ĐẦU NGÀY:
- Vĩ mô thế giới: {inter_str} | Tin vĩ mô: {news_str}
- VN-Index: {vni_str}
- Dữ liệu cổ phiếu:
{stocks_text}

YÊU CẦU BẮT BUỘC:
- Độ dài chuẩn: 850 - 1.100 ký tự. Ngắn gọn, dứt khoát, vào thẳng lệnh.
- Phải có GIÁ CỤ THỂ (ví dụ 32.500 đ, 65.500 đ, không nói "vùng giá đỏ" chung chung).

BẮT BUỘC TRÌNH BÀY ĐÚNG 4 MỤC SAU:
☕ SẾP DUYỆT NHANH KẾ HOẠCH PHIÊN HÔM NAY:

⚠️ 1. ĐÁNH GIÁ 1 CÂU:
(Thị trường XẤU hay TỐT? Chiến lược chính hôm nay: PHÒNG THỦ hay TẤN CÔNG? Tâm lý ATO?)

📋 2. CÁC LỆNH CHỜ SẾP DUYỆT SÁNG NAY:
• [MUA RÌNH RẬP] (Chọn 1 mã có dòng tiền khỏe nhất): Kê mua giá [Giá cụ thể] (tỷ trọng 20% NAV) | Mục tiêu: [Giá TP] | Cắt lỗ gãy: [Giá SL]. Lý do: 1 câu ngắn.
• [BÁN / HẠ TỶ TRỌNG] (Chọn 1 mã rủi ro/bị xả mạnh nhất): Hồi lên vùng [Giá bán cụ thể] là sút ngay 50% vị thế, tuyệt đối không trung bình giá. Lý do: 1 câu ngắn.
• [CHỜ NỔ VOL] (Chọn 1 mã đang siết nền chặt nhất): Kế hoạch giá gom và giá mua gia tăng khi bứt phá.

🚨 3. MỐC BÁO ĐỘNG ĐỎ CỦA PHIÊN:
• Kịch bản sập: Nếu trước 10:30 VN-Index thủng mốc [Mốc điểm hỗ trợ cụ thể] -> Khóa mua toàn danh mục, hạ margin về 0.
• Kịch bản ổn định: Điều kiện rút chân giữ vững mốc hỗ trợ và giữ danh mục."""

    candidate_models = [
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 750
        }
    }
    encoded_data = json.dumps(payload).encode('utf-8')

    for model_name in candidate_models:
        clean_model = model_name if not model_name.startswith("models/") else model_name.replace("models/", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=encoded_data, headers={'content-type': 'application/json'})

        for sub_attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    res_data = json.loads(resp.read().decode())
                    text_result = res_data['candidates'][0]['content']['parts'][0]['text']
                    if text_result and len(text_result.strip()) > 80:
                        return text_result.strip()
            except urllib.error.HTTPError as e:
                if e.code in (503, 429, 404):
                    time.sleep(1)
                    break
                time.sleep(1)
            except Exception:
                time.sleep(1)

    return generate_action_orders_fallback(stock_summaries, vnindex, intermarket, news)


# ================= 6. GIAO NHẬN TIN NHẮN TELEGRAM =================
def send_telegram(message: str, bot_token: str, chat_id: str):
    """Gửi kế hoạch hành động duyệt lệnh trọn vẹn về Telegram"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message.strip(),
        "parse_mode": "Markdown"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'content-type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            print("[+] Đã gửi trọn vẹn kế hoạch duyệt lệnh về Telegram thành công!")
    except urllib.error.HTTPError as e:
        print(f"[!] Lỗi Markdown ({e.code}). Chuyển sang Plaintext...")
        payload.pop("parse_mode", None)
        req2 = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'content-type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req2, timeout=12):
                print("[+] Đã gửi trọn vẹn kế hoạch duyệt lệnh về Telegram (Plaintext) thành công!")
        except Exception as ex:
            print(f"[!] Lỗi khi gửi Telegram: {ex}")


# ================= 7. ĐIỀU PHỐI TOÀN BỘ LUỒNG PIPELINE =================
def run_pipeline():
    start_time = time.time()
    print("=" * 65)
    print("🚀 BẮT ĐẦU CHẠY KẾ HOẠCH HÀNH ĐỘNG THAM MƯU CHO GIÁM ĐỐC")
    print(f"⏰ Kích hoạt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # 1. Thu thập liên thị trường & Tin tức vĩ mô
    print("[*] 1/4. Đang thu thập liên thị trường & tin tức vĩ mô...")
    intermarket = fetch_intermarket_pulse()
    news = fetch_macro_news()

    # 2. Thu thập dữ liệu chỉ số VN-INDEX
    print("[*] 2/4. Đang lấy trạng thái chỉ số VN-INDEX...")
    vnindex = fetch_vnindex_summary()

    # 3. Thu thập và phân tích danh mục cổ phiếu đa luồng
    print(f"[*] 3/4. Đang phân tích kỹ thuật {len(WATCHLIST)} mã trụ...")
    stock_summaries = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_stock_data_pro, WATCHLIST))

    for res in results:
        if res:
            stock_summaries.append(res)

    if not stock_summaries:
        print("[!] Không lấy được dữ liệu cổ phiếu.")
        return

    # 4. Soạn thảo bảng lệnh duyệt qua AI Chief of Staff
    print("[*] 4/4. Đang soạn bảng lệnh hành động dứt khoát cho Giám đốc...")
    if not GEMINI_API_KEY:
        briefing = generate_action_orders_fallback(stock_summaries, vnindex, intermarket, news)
    else:
        briefing = ask_gemini_action_orders(stock_summaries, vnindex, intermarket, news, GEMINI_API_KEY)

    # 5. Gửi bản tin về Telegram
    print("[*] Đang gửi kế hoạch duyệt lệnh về Telegram Sếp...")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram(briefing, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    else:
        print("[!] Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")

    elapsed = time.time() - start_time
    print(f"🎉 HOÀN THÀNH BẢN KẾ HOẠCH TRONG {elapsed:.1f} GIÂY!")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline()
