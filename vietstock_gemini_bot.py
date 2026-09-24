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

# Danh mục theo dõi tùy biến qua .env (hoặc mặc định rổ cổ phiếu trụ cột)
ENV_WATCHLIST = get_env_var("WATCHLIST", "")
if ENV_WATCHLIST:
    WATCHLIST = [s.strip().upper() for s in ENV_WATCHLIST.split(",") if s.strip()]
else:
    WATCHLIST = ["FPT", "HPG", "VCB", "SSI", "MWG", "TCB", "VHM", "MBB"]

# Phân loại nhóm ngành cốt lõi
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
    """Tính Exponential Moving Average (EMA) cho danh sách giá"""
    if len(prices) < period:
        return prices
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append((p - ema[-1]) * multiplier + ema[-1])
    return ema


# ================= 1. THU THẬP BỐI CẢNH VĨ MÔ & LIÊN THỊ TRƯỜNG =================
def fetch_intermarket_pulse() -> dict:
    """Lấy dữ liệu tài chính quốc tế đêm qua (Dow Jones, DXY, Dầu thô, Vàng)"""
    tickers = {
        "Dow Jones": "^DJI",
        "DXY": "DX-Y.NYB",
        "Dầu WTI": "CL=F",
        "Vàng": "GC=F"
    }
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
    """Lấy 2 tin tức tài chính chứng khoán đáng chú ý nhất sáng sớm từ CafeF RSS"""
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


# ================= 2. THU THẬP VÀ PHÂN TÍCH CHỈ SỐ VN-INDEX =================
def fetch_vnindex_summary() -> dict:
    """Lấy số liệu và chỉ báo kỹ thuật của chỉ số thị trường chung VN-INDEX"""
    try:
        now = int(time.time())
        from_time = now - 120 * 86400
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from={from_time}&to={now}&symbol=VNINDEX&resolution=1D"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            closes = [c for c in data.get('c', []) if c is not None]
            volumes = [v for v in data.get('v', []) if v is not None]
            highs = [h for h in data.get('h', []) if h is not None]
            lows = [l for l in data.get('l', []) if l is not None]

            if len(closes) >= 20:
                latest = closes[-1]
                prev = closes[-2]
                pct = ((latest - prev) / prev) * 100
                ma20 = sum(closes[-20:]) / 20
                ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
                avg_vol20 = sum(volumes[-20:]) / 20
                vol_ratio = volumes[-1] / avg_vol20 if avg_vol20 > 0 else 1.0

                # RSI 14
                deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
                gains = [d if d > 0 else 0 for d in deltas[-14:]]
                losses = [-d if d < 0 else 0 for d in deltas[-14:]]
                avg_gain = sum(gains) / 14 if sum(gains) > 0 else 0.001
                avg_loss = sum(losses) / 14 if sum(losses) > 0 else 0.001
                rsi = 100 - (100 / (1 + (avg_gain / avg_loss)))

                swing_res = max(highs[-20:])
                swing_sup = min(lows[-20:])

                trend = "Trên MA20" if latest >= ma20 else "Dưới MA20"

                return {
                    "name": "VN-INDEX",
                    "close": round(latest, 2),
                    "change_pct": round(pct, 2),
                    "ma20": round(ma20, 2),
                    "ma50": round(ma50, 2),
                    "rsi": round(rsi, 1),
                    "vol_ratio": round(vol_ratio, 2),
                    "trend": trend,
                    "support": round(swing_sup, 2),
                    "resistance": round(swing_res, 2)
                }
    except Exception:
        pass

    # Dự phòng qua ETF VN30
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/E1VFVN30.VN?interval=1d&range=3mo"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            res = json.loads(resp.read().decode())
            quote = res['chart']['result'][0]['indicators']['quote'][0]
            closes = [c for c in quote['close'] if c is not None]
            if len(closes) >= 20:
                latest = closes[-1]
                prev = closes[-2]
                pct = ((latest - prev) / prev) * 100
                ma20 = sum(closes[-20:]) / 20
                return {
                    "name": "ETF VN30",
                    "close": round(latest, 0),
                    "change_pct": round(pct, 2),
                    "ma20": round(ma20, 0),
                    "ma50": round(ma20, 0),
                    "rsi": 50.0,
                    "vol_ratio": 1.0,
                    "trend": "Trên MA20" if latest >= ma20 else "Dưới MA20",
                    "support": round(ma20 * 0.97, 0),
                    "resistance": round(ma20 * 1.03, 0)
                }
    except Exception:
        pass
    return None


# ================= 3. PHÂN TÍCH KỸ THUẬT DANH MỤC CỔ PHIẾU =================
def fetch_stock_data_pro(ticker: str) -> dict:
    """Phân tích kỹ thuật cốt lõi: MA20/50, RSI, MACD, Bollinger Bands, Swing Levels"""
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
            
            # MA20, MA50
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
            trend_ma = "Trên MA20" if latest_price >= ma20 else "Dưới MA20"
            
            # RSI 14
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas[-14:]]
            losses = [-d if d < 0 else 0 for d in deltas[-14:]]
            avg_gain = sum(gains) / 14 if sum(gains) > 0 else 0.001
            avg_loss = sum(losses) / 14 if sum(losses) > 0 else 0.001
            rsi_14 = 100 - (100 / (1 + (avg_gain / avg_loss)))
            
            # MACD (12, 26, 9)
            ema12 = calc_ema(closes, 12)
            ema26 = calc_ema(closes, 26)
            macd_series = [e12 - e26 for e12, e26 in zip(ema12[26-12:], ema26)]
            signal_series = calc_ema(macd_series, 9)
            macd_val = macd_series[-1]
            signal_val = signal_series[-1]
            hist = macd_val - signal_val
            prev_hist = macd_series[-2] - signal_series[-2] if len(macd_series) >= 2 else hist
            
            if hist > 0 and prev_hist <= 0:
                macd_status = "Cắt lên Signal (MUA)"
            elif hist > 0:
                macd_status = "Dương (Khỏe)"
            elif hist < 0 and prev_hist >= 0:
                macd_status = "Cắt xuống Signal (BÁN)"
            else:
                macd_status = "Âm (Yếu)"

            # Bollinger Bands
            subset20 = closes[-20:]
            variance = sum((x - ma20)**2 for x in subset20) / 20
            std_dev = math.sqrt(variance)
            upper_bb = ma20 + 2 * std_dev
            lower_bb = ma20 - 2 * std_dev
            bandwidth = ((upper_bb - lower_bb) / ma20) * 100
            
            if bandwidth < 7.5:
                bb_status = "Siết nền (Sắp nổ Vol)"
            elif latest_price >= upper_bb * 0.99:
                bb_status = "Chạm dải trên"
            elif latest_price <= lower_bb * 1.01:
                bb_status = "Quá bán dải dưới"
            else:
                bb_status = "Bình thường"

            # Support / Resistance 20 phiên
            swing_res = max(highs[-20:]) if highs else ma20 * 1.05
            swing_sup = min(lows[-20:]) if lows else ma20 * 0.95

            # Price Action nến
            o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
            body = abs(c - o)
            lower_shadow = min(o, c) - l
            upper_shadow = h - max(o, c)
            if lower_shadow >= 1.8 * body and body > 0:
                candle_desc = "Rút chân đáy"
            elif upper_shadow >= 1.8 * body and body > 0:
                candle_desc = "Cụt đầu bị ép"
            elif c > o and body / (h - l + 0.001) >= 0.7:
                candle_desc = "Nến xanh đặc"
            else:
                candle_desc = "Tích lũy"

            # Volume
            latest_vol = volumes[-1]
            avg_vol_20 = sum(volumes[-20:]) / 20
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

            return {
                "ticker": ticker,
                "sector": SECTOR_MAP.get(ticker, "Khác"),
                "price": latest_price,
                "change_pct": round(pct_change, 2),
                "rsi": round(rsi_14, 1),
                "ma20": round(ma20, 1),
                "ma50": round(ma50, 1),
                "trend_ma": trend_ma,
                "macd_status": macd_status,
                "macd_hist": round(hist, 2),
                "bb_status": bb_status,
                "bandwidth": round(bandwidth, 1),
                "candle": candle_desc,
                "support": round(swing_sup, 0),
                "resistance": round(swing_res, 0),
                "vol_ratio": round(vol_ratio, 2)
            }
    except Exception:
        return None


# ================= 4. BỘ PHÂN TÍCH TÓM TẮT DỰ PHÒNG =================
def generate_quantitative_briefing_pro(stock_summaries: list, vnindex: dict, intermarket: dict, news: list) -> str:
    """Tạo bản tin tóm tắt súc tích dự phòng (< 1.200 ký tự) khi AI ngắt kết nối"""
    lines = []
    
    # 1. Vĩ mô
    lines.append("🌐 *1. VĨ MÔ THẾ GIỚI:*")
    if intermarket:
        inter_items = [f"{k}: `{v['price']:,.1f}` ({v['pct']:+0.2f}%)" for k, v in intermarket.items()]
        lines.append("• " + " | ".join(inter_items))
    if news:
        lines.append(f"• Tin chính: _{news[0]}_")

    # 2. VN-INDEX
    lines.append("\n📊 *2. VN-INDEX:*")
    if vnindex:
        lines.append(f"• Điểm số: `{vnindex['close']:,.2f}` ({vnindex['change_pct']:+0.2f}%) | {vnindex['trend']} | Vol: {vnindex['vol_ratio']:.1f}x TB20P")
        lines.append(f"• Vùng kỹ thuật: Hỗ trợ cứng `{vnindex['support']:,.0f}` | Kháng cự `{vnindex['resistance']:,.0f}`")
    else:
        lines.append("• Trạng thái: Tích lũy phân hóa.")

    # 3. Dòng tiền ngành
    lines.append("\n🎯 *3. DÒNG TIỀN NGÀNH:*")
    by_sec = {}
    for s in stock_summaries:
        by_sec.setdefault(s['sector'], []).append(s)
    for sec, stocks in by_sec.items():
        stk_str = ", ".join([f"*{s['ticker']}* ({s['change_pct']:+0.1f}%)" for s in stocks])
        lines.append(f"• {sec}: {stk_str}")

    # 4. Top picks
    lines.append("\n🚀 *4. CHIẾN LƯỢC & TOP PICKS:*")
    bulls = [s for s in stock_summaries if s['macd_hist'] > 0 and 45 <= s['rsi'] <= 68]
    if bulls:
        top = bulls[0]
        lines.append(f"• ⭐ *{top['ticker']}* ({top['sector']}): Mua `{top['price']*0.985:,.0f} - {top['price']*1.005:,.0f}` | Target: `{top['resistance']:,.0f}` | Stoploss: `{top['support']*0.98:,.0f}`")
    else:
        top = stock_summaries[0]
        lines.append(f"• *{top['ticker']}*: Canh tích lũy quanh MA20 (`{top['ma20']:,.0f} đ`).")

    # 5. Tỷ trọng
    lines.append("\n🛡️ *5. TỶ TRỌNG & HÀNH ĐỘNG:*")
    lines.append("• Tỷ trọng: *50% Cổ phiếu / 50% Tiền mặt*.")
    lines.append("• Hành động: Không mua đuổi ATO xanh; chỉ gom từng phần khi cổ phiếu test hỗ trợ thành công.")

    return "\n".join(lines)


# ================= 5. AI CHUYÊN GIA: BẢN TIN TÓM TẮT SIÊU GỌN =================
def ask_gemini_pro(stock_summaries: list, vnindex: dict, intermarket: dict, news: list, api_key: str) -> str:
    """Tạo bản tin Flash Briefing siêu súc tích (< 1.300 ký tự), đọc lướt trong 45 giây"""
    # Dữ liệu vĩ mô
    intermarket_str = ", ".join([f"{k}: {v['price']:,.1f} ({v['pct']:+0.2f}%)" for k, v in intermarket.items()]) if intermarket else "Ổn định"
    news_str = " | ".join(news[:2]) if news else "Không có tin giật gân"

    # Dữ liệu VN-INDEX
    if vnindex:
        vni_str = f"{vnindex['close']:,.2f} đ ({vnindex['change_pct']:+0.2f}%), {vnindex['trend']}, Vol={vnindex['vol_ratio']}x TB20P. Hỗ trợ={vnindex['support']:,.0f}, Cản={vnindex['resistance']:,.0f}"
    else:
        vni_str = "Tích lũy quanh hỗ trợ"

    # Dữ liệu cổ phiếu
    stocks_lines = []
    for s in stock_summaries:
        stocks_lines.append(
            f"{s['ticker']} ({s['sector']}): {s['price']:,.0f} đ ({s['change_pct']:+0.1f}%), "
            f"RSI={s['rsi']}, {s['trend_ma']}, MACD={s['macd_status']}, BB={s['bb_status']}, "
            f"Nến={s['candle']}, Vol={s['vol_ratio']}x, HT={s['support']:,.0f}, Cản={s['resistance']:,.0f}"
        )
    stocks_str = "\n".join(stocks_lines)

    prompt = f"""Bạn là Giám đốc Phân tích Chiến lược Chứng khoán. Hãy TÓM TẮT BẢN TIN BUỔI SÁNG thành 1 BÁO CÁO NHANH (FLASH BRIEFING) GỌN GÀNG, SẮC BÉN, ĐI THẲNG VÀO TRỌNG TÂM.

TUYỆT ĐỐI TUÂN THỦ:
- KHÔNG viết lời chào hỏi, mở bài ("Chào anh chị...", "Dưới đây là..."), KHÔNG viết kết bài sáo rỗng ("Chúc thành công...").
- Độ dài BẮT BUỘC: 1.000 đến 1.400 ký tự (vừa vặn 1 tin nhắn Telegram đọc trong 45 giây).
- Dùng gạch đầu dòng, icon rõ ràng, số liệu giá chuẩn (ví dụ: 66.000 đ).

DỮ LIỆU ĐẦU VÀO:
- Vĩ mô: {intermarket_str}
- Tin sáng: {news_str}
- VN-Index: {vni_str}
- Cổ phiếu:
{stocks_str}

BẮT BUỘC TRÌNH BÀY CHÍNH XÁC 5 MỤC SAU:
🌐 1. VĨ MÔ THẾ GIỚI: (2 dòng: biến động DJ, DXY, Dầu và tin vĩ mô nổi bật)
📊 2. VN-INDEX: (2 dòng: trạng thái thị trường, vùng hỗ trợ then chốt & cản)
🎯 3. DÒNG TIỀN NGÀNH: (3 dòng: điểm nhanh nhóm Ngân hàng, Công nghệ/Bán lẻ, Thép/BĐS)
🚀 4. CHIẾN LƯỢC & TOP PICKS: (Chọn 1-2 mã đẹp nhất: Mã - Vùng mua - Mục tiêu - Cắt lỗ; và 1 cảnh báo mã yếu)
🛡️ 5. TỶ TRỌNG & HÀNH ĐỘNG: (Tỷ trọng % Cổ/Tiền; 1 lời khuyên thực chiến phiên ATO)"""

    candidate_models = [
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 900
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

    return generate_quantitative_briefing_pro(stock_summaries, vnindex, intermarket, news)


# ================= 6. GIAO NHẬN TIN NHẮN TRỌN VẸN QUA TELEGRAM =================
def send_telegram(message: str, bot_token: str, chat_id: str):
    """Gửi bản tin tóm tắt hoàn chỉnh về Telegram trong 1 tin nhắn duy nhất, không cắt xén"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    full_message = (
        f"☕ *BẢN TIN SÁNG {today_str} | FLASH BRIEFING*\n\n"
        f"{message.strip()}"
    )

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
            print("[+] Đã gửi trọn vẹn bản tin tóm tắt về Telegram thành công!")
    except urllib.error.HTTPError as e:
        print(f"[!] Lỗi Markdown ({e.code}). Chuyển sang gửi Plaintext...")
        payload.pop("parse_mode", None)
        req2 = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'content-type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req2, timeout=12):
                print("[+] Đã gửi trọn vẹn bản tin tóm tắt về Telegram (Plaintext) thành công!")
        except Exception as ex:
            print(f"[!] Lỗi khi gửi Telegram: {ex}")


# ================= 7. ĐIỀU PHỐI TOÀN BỘ LUỒNG PIPELINE =================
def run_pipeline():
    start_time = time.time()
    print("=" * 65)
    print("🚀 BẮT ĐẦU CHẠY BẢN TIN TÓM TẮT SÁNG (FLASH BRIEFING)")
    print(f"⏰ Kích hoạt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # 1. Thu thập liên thị trường & Tin tức vĩ mô
    print("[*] 1/4. Đang thu thập liên thị trường & tin tức sáng sớm...")
    intermarket = fetch_intermarket_pulse()
    news = fetch_macro_news()

    # 2. Thu thập dữ liệu chỉ số VN-INDEX
    print("[*] 2/4. Đang thu thập chỉ số VN-INDEX...")
    vnindex = fetch_vnindex_summary()
    if vnindex:
        print(f"    -> VN-INDEX: {vnindex['close']:,.2f} đ ({vnindex['change_pct']:+0.2f}%), {vnindex.get('trend')}")

    # 3. Thu thập và phân tích danh mục cổ phiếu đa luồng
    print(f"[*] 3/4. Đang phân tích kỹ thuật ({len(WATCHLIST)} mã)...")
    stock_summaries = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_stock_data_pro, WATCHLIST))

    for res in results:
        if res:
            stock_summaries.append(res)

    if not stock_summaries:
        print("[!] Không lấy được dữ liệu cổ phiếu nào.")
        return

    # 4. Phân tích tóm tắt siêu gọn qua AI
    print("[*] 4/4. Đang tạo bản tin tóm tắt súc tích qua AI...")
    if not GEMINI_API_KEY:
        briefing = generate_quantitative_briefing_pro(stock_summaries, vnindex, intermarket, news)
    else:
        briefing = ask_gemini_pro(stock_summaries, vnindex, intermarket, news, GEMINI_API_KEY)

    # 5. Gửi bản tin về Telegram
    print("[*] Đang gửi bản tin về Telegram...")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram(briefing, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    else:
        print("[!] Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")

    elapsed = time.time() - start_time
    print(f"🎉 HOÀN THÀNH BẢN TIN TÓM TẮT TRONG {elapsed:.1f} GIÂY!")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline()
