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


# ================= 1. THU THẬP VĨ MÔ & THẾ GIỚI =================
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
                    "trend": "Đang chỉnh dưới MA20" if latest < ma20 else "Ổn định trên MA20"
                }
    except Exception:
        pass
    return None


# ================= 3. PHÂN TÍCH KỸ THUẬT DANH MỤC =================
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

            # Phân loại trạng thái đèn giao thông cho Sếp
            if pct_change > 1.5 or (hist > 0 and latest_price >= ma20):
                traffic_light = "🟢 Khỏe"
                note = "Dòng tiền vào tốt" if vol_ratio >= 1.1 else "Giữ nền xanh"
            elif is_squeeze or (abs(pct_change) < 1.0 and 45 <= rsi <= 60):
                traffic_light = "🟡 Nén chờ nổ"
                note = "Bollinger thắt chặt" if is_squeeze else "Tích lũy cạn vol"
            else:
                traffic_light = "🔴 Yếu"
                note = "RSI quá bán sâu" if rsi < 32 else ("Áp lực xả mạnh" if vol_ratio >= 1.5 else "Thủng MA20")

            return {
                "ticker": ticker,
                "price": latest_price,
                "change_pct": round(pct_change, 2),
                "rsi": round(rsi, 1),
                "ma20": round(ma20, 0),
                "support": round(min(lows[-20:]), 0),
                "resistance": round(max(highs[-20:]), 0),
                "traffic_light": traffic_light,
                "note": note,
                "vol_ratio": round(vol_ratio, 1),
                "macd_buy": macd_buy,
                "is_hammer": is_hammer
            }
    except Exception:
        return None


# ================= 4. BỘ PHÂN TÍCH THƯ KÝ DỰ PHÒNG =================
def generate_secretary_briefing_fallback(stock_summaries: list, vnindex: dict, intermarket: dict, news: list) -> str:
    """Tạo báo cáo nhanh chuẩn thư ký (< 900 ký tự) khi AI ngắt kết nối"""
    lines = []
    lines.append("Gửi Sếp Báo cáo nhanh đầu ngày:\n")
    
    # 1. Nhiệt kế thị trường
    lines.append("🌡️ *1. NHIỆT KẾ THỊ TRƯỜNG:*")
    if vnindex:
        lines.append(f"• VN-Index: `{vnindex['close']:,.2f}` ({vnindex['change_pct']:+0.2f}%) | {vnindex['trend']}. Hỗ trợ sống còn: `{vnindex['support']:,.0f}` (MA50 `{vnindex['ma50']:,.0f}`).")
    if intermarket:
        inter_str = " | ".join([f"{k}: `{v['price']:,.1f}` ({v['pct']:+0.2f}%)" for k, v in intermarket.items()])
        lines.append(f"• Thế giới: {inter_str}")

    # 2. Tình hình các mã trụ
    lines.append("\n🧭 *2. TÌNH HÌNH CÁC MÃ TRỤ:*")
    green = [s for s in stock_summaries if "🟢" in s['traffic_light']]
    yellow = [s for s in stock_summaries if "🟡" in s['traffic_light']]
    red = [s for s in stock_summaries if "🔴" in s['traffic_light']]

    if green:
        lines.append("• 🟢 *Khỏe*: " + ", ".join([f"*{s['ticker']}* ({s['change_pct']:+0.1f}%, {s['note']})" for s in green]))
    if yellow:
        lines.append("• 🟡 *Nén chờ nổ*: " + ", ".join([f"*{s['ticker']}* ({s['note']})" for s in yellow]))
    if red:
        lines.append("• 🔴 *Yếu / Cần chú ý*: " + ", ".join([f"*{s['ticker']}* ({s['change_pct']:+0.1f}%, {s['note']})" for s in red]))

    # 3. Đề xuất hành động cho Sếp
    lines.append("\n🎯 *3. ĐỀ XUẤT HÀNH ĐỘNG HÔM NAY CHO SẾP:*")
    picks = green if green else yellow
    if picks:
        p = picks[0]
        lines.append(f"• 🛒 *Canh gom*: *{p['ticker']}* quanh `{p['price']*0.985:,.0f} - {p['price']:,.0f} đ` (Target: `{p['resistance']:,.0f}`).")
    if red:
        lines.append(f"• ⚠️ *Cần tránh*: Tránh bắt đáy sớm *{red[0]['ticker']}*, canh nhịp hồi hạ tỷ trọng.")
    lines.append("• 💼 *Quản lý vốn*: Duy trì *50% Cổ / 50% Tiền*. Chưa dùng margin cho đến khi VN-Index giữ vững hỗ trợ.")

    return "\n".join(lines)


# ================= 5. AI THƯ KÝ: BÁO CÁO GIÁM ĐỐC TRỰC QUAN =================
def ask_gemini_secretary(stock_summaries: list, vnindex: dict, intermarket: dict, news: list, api_key: str) -> str:
    """Đóng vai Thư ký / Trợ lý Đầu tư riêng của Giám đốc, tóm tắt trực quan nhìn là hiểu ngay"""
    inter_str = ", ".join([f"{k}: {v['price']:,.1f} ({v['pct']:+0.2f}%)" for k, v in intermarket.items()]) if intermarket else "Ổn định"
    news_str = news[0] if news else "Không có tin giật gân"
    vni_str = f"{vnindex['close']:,.2f} đ ({vnindex['change_pct']:+0.2f}%), {vnindex['trend']}, Hỗ trợ MA50={vnindex['ma50']:,.0f}, Đáy={vnindex['support']:,.0f}" if vnindex else "Tích lũy"

    stocks_text = "\n".join([
        f"- {s['ticker']}: Giá {s['price']:,.0f} đ ({s['change_pct']:+0.1f}%), {s['traffic_light']}, {s['note']}, RSI={s['rsi']}, Vol={s['vol_ratio']}x"
        for s in stock_summaries
    ])

    prompt = f"""Bạn là Thư ký kiêm Trợ lý Đầu tư riêng của Giám đốc (Sếp).
Nhiệm vụ: Soạn một bản BÁO CÁO NHANH ĐẦU NGÀY gửi Sếp qua Telegram để Sếp bận rộn 'liếc qua 15-20 giây là hiểu ngay bức tranh thị trường và biết cần chỉ đạo/hành động gì'.

DỮ LIỆU ĐẦU NGÀY:
- Vĩ mô thế giới: {inter_str} | Điểm tin: {news_str}
- VN-Index: {vni_str}
- Các mã theo dõi:
{stocks_text}

YÊU CẦU BẮT BUỘC:
- Xưng hô lịch thiệp chuẩn trợ lý báo cáo Sếp ("Gửi Sếp Báo cáo nhanh đầu ngày:").
- CỰC KỲ NGẮN GỌN, TRỰC QUAN (độ dài đúng 800 - 1.000 ký tự). Nhìn lướt là hiểu ngay.
- Phân nhóm bằng màu sắc đèn giao thông rõ ràng: 🟢 Khỏe (Dòng tiền vào), 🟡 Nén chờ nổ (Tích lũy), 🔴 Yếu (Bị xả/Cần chú ý).

CẤU TRÚC CHÍNH XÁC:
Gửi Sếp Báo cáo nhanh đầu ngày:

🌡️ 1. NHIỆT KẾ THỊ TRƯỜNG:
• VN-Index: [Điểm số] ([%]) | [1 câu đánh giá trạng thái và mốc điểm sống còn cần giữ]
• Vĩ mô thế giới: [1 dòng tóm tắt Dow Jones, Dầu, tin chính ảnh hưởng ATO]

🧭 2. TÌNH HÌNH CÁC MÃ TRỤ:
• 🟢 Khỏe (Hút tiền): [Các mã + lý do 1 câu]
• 🟡 Nén chặt (Sắp nổ): [Các mã + lý do 1 câu]
• 🔴 Yếu / Rủi ro: [Các mã + lý do 1 câu]

🎯 3. ĐỀ XUẤT HÀNH ĐỘNG HÔM NAY CHO SẾP:
• 🛒 Canh gom: [Chọn 1-2 mã ngon nhất: Vùng giá gom - Mục tiêu]
• ⚠️ Cần tránh / Hạ bớt: [Mã rủi ro cần tránh hoặc canh hồi bán]
• 💼 Quản lý vốn: [Tỷ lệ % Cổ / % Tiền, có dùng margin không]"""

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

    return generate_secretary_briefing_fallback(stock_summaries, vnindex, intermarket, news)


# ================= 6. GIAO NHẬN TIN NHẮN TELEGRAM =================
def send_telegram(message: str, bot_token: str, chat_id: str):
    """Gửi báo cáo tóm tắt trọn vẹn về Telegram trong 1 tin nhắn duy nhất"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    full_message = f"📋 *BÁO CÁO ĐẦU NGÀY GỬI SẾP ({today_str})*\n\n{message.strip()}"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": full_message,
        "parse_mode": "Markdown"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'content-type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            print("[+] Đã gửi trọn vẹn báo cáo thư ký về Telegram thành công!")
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
                print("[+] Đã gửi trọn vẹn báo cáo thư ký về Telegram (Plaintext) thành công!")
        except Exception as ex:
            print(f"[!] Lỗi khi gửi Telegram: {ex}")


# ================= 7. ĐIỀU PHỐI TOÀN BỘ LUỒNG PIPELINE =================
def run_pipeline():
    start_time = time.time()
    print("=" * 65)
    print("🚀 BẮT ĐẦU CHẠY BÁO CÁO THƯ KÝ GỬI GIÁM ĐỐC")
    print(f"⏰ Kích hoạt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # 1. Thu thập liên thị trường & Tin tức vĩ mô
    print("[*] 1/4. Đang thu thập liên thị trường & tin tức...")
    intermarket = fetch_intermarket_pulse()
    news = fetch_macro_news()

    # 2. Thu thập dữ liệu chỉ số VN-INDEX
    print("[*] 2/4. Đang lấy trạng thái chỉ số VN-INDEX...")
    vnindex = fetch_vnindex_summary()

    # 3. Thu thập và phân tích danh mục cổ phiếu đa luồng
    print(f"[*] 3/4. Đang quét dữ liệu {len(WATCHLIST)} mã trụ...")
    stock_summaries = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_stock_data_pro, WATCHLIST))

    for res in results:
        if res:
            stock_summaries.append(res)

    if not stock_summaries:
        print("[!] Không lấy được dữ liệu cổ phiếu.")
        return

    # 4. Phân tích tóm tắt siêu trực quan qua AI Thư ký
    print("[*] 4/4. Đang soạn báo cáo trực quan cho Giám đốc...")
    if not GEMINI_API_KEY:
        briefing = generate_secretary_briefing_fallback(stock_summaries, vnindex, intermarket, news)
    else:
        briefing = ask_gemini_secretary(stock_summaries, vnindex, intermarket, news, GEMINI_API_KEY)

    # 5. Gửi bản tin về Telegram
    print("[*] Đang gửi báo cáo về Telegram Sếp...")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram(briefing, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    else:
        print("[!] Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")

    elapsed = time.time() - start_time
    print(f"🎉 HOÀN THÀNH BÁO CÁO TRONG {elapsed:.1f} GIÂY!")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline()
