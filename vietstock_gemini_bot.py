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

# Danh mục theo dõi tùy biến qua .env (hoặc mặc định rổ cổ phiếu trụ cột đa ngành)
ENV_WATCHLIST = get_env_var("WATCHLIST", "")
if ENV_WATCHLIST:
    WATCHLIST = [s.strip().upper() for s in ENV_WATCHLIST.split(",") if s.strip()]
else:
    WATCHLIST = ["FPT", "HPG", "VCB", "SSI", "MWG", "TCB", "VHM", "MBB"]

# Bản đồ phân loại nhóm ngành cốt lõi
SECTOR_MAP = {
    "FPT": "Công nghệ",
    "MWG": "Bán lẻ",
    "FRT": "Bán lẻ",
    "DGC": "Hóa chất",
    "VCB": "Ngân hàng",
    "TCB": "Ngân hàng",
    "MBB": "Ngân hàng",
    "CTG": "Ngân hàng",
    "STB": "Ngân hàng",
    "ACB": "Ngân hàng",
    "SSI": "Chứng khoán",
    "VND": "Chứng khoán",
    "VCI": "Chứng khoán",
    "HCM": "Chứng khoán",
    "HPG": "Thép",
    "HSG": "Thép",
    "NKG": "Thép",
    "VHM": "Bất động sản",
    "VIC": "Bất động sản",
    "VRE": "Bất động sản",
    "DIG": "Bất động sản",
    "PDR": "Bất động sản",
    "KDH": "Bất động sản",
    "NLG": "Bất động sản",
    "PVS": "Dầu khí",
    "PVD": "Dầu khí",
    "BSR": "Dầu khí",
    "GAS": "Dầu khí",
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
    """Lấy dữ liệu các chỉ số tài chính quốc tế đêm qua (Dow Jones, DXY, Dầu thô, Vàng)"""
    tickers = {
        "Dow Jones": "^DJI",
        "DXY (USD Index)": "DX-Y.NYB",
        "Dầu WTI": "CL=F",
        "Vàng Thế Giới": "GC=F"
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
    """Thu thập 3-4 tin tức tài chính chứng khoán tiêu biểu sáng sớm từ CafeF RSS"""
    url = "https://cafef.vn/thi-truong-chung-khoan.rss"
    headlines = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            root = ET.fromstring(resp.read())
            items = root.findall('.//item')
            for item in items[:4]:
                title_elem = item.find('title')
                if title_elem is not None and title_elem.text:
                    clean_title = title_elem.text.strip().replace("\n", " ")
                    headlines.append(clean_title)
    except Exception as e:
        print(f"[!] Không lấy được RSS CafeF: {e}")
    return headlines


# ================= 2. THU THẬP VÀ PHÂN TÍCH CHỈ SỐ VN-INDEX =================
def fetch_vnindex_summary() -> dict:
    """Lấy số liệu và tính chỉ báo kỹ thuật của chỉ số thị trường chung VN-INDEX"""
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
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

                # Hỗ trợ / Kháng cự 20 phiên
                swing_res = max(highs[-20:])
                swing_sup = min(lows[-20:])

                trend = "TRÊN MA20 (Uptrend)" if latest >= ma20 else "DƯỚI MA20 (Điều chỉnh/Thận trọng)"

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
    except Exception as e:
        print(f"[!] Lỗi khi lấy VN-INDEX qua DNSE: {e}. Thử phương án dự phòng...")

    # Dự phòng: Lấy qua ETF VN30 (E1VFVN30.VN) trên Yahoo Finance
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
                ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
                return {
                    "name": "ETF VN30 (Đại diện thị trường)",
                    "close": round(latest, 0),
                    "change_pct": round(pct, 2),
                    "ma20": round(ma20, 0),
                    "ma50": round(ma50, 0),
                    "rsi": 50.0,
                    "vol_ratio": 1.0,
                    "trend": "TRÊN MA20" if latest >= ma20 else "DƯỚI MA20",
                    "support": round(ma20 * 0.97, 0),
                    "resistance": round(ma20 * 1.03, 0)
                }
    except Exception:
        pass
    return None


# ================= 3. PHÂN TÍCH KỸ THUẬT CHUYÊN SÂU TỪNG CỔ PHIẾU =================
def fetch_stock_data_pro(ticker: str) -> dict:
    """
    Phân tích kỹ thuật đa chiều chuẩn CMT (Chartered Market Technician):
    - Trend: MA20, MA50
    - Momentum: RSI(14), MACD(12,26,9) & Signal Line
    - Volatility: Bollinger Bands (20,2), Bandwidth Squeeze
    - Price Action: Nến tín hiệu (Rút chân / Cụt đầu / Thân đặc)
    - Levels: Đỉnh/Đáy ngắn hạn (Swing High/Low 20 phiên)
    """
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
            
            # Đường MA20, MA50
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
            trend_ma = "TRÊN MA20" if latest_price >= ma20 else "DƯỚI MA20"
            ma_cross = "Golden Cross (MA20 > MA50)" if ma20 >= ma50 else "Death Cross (MA20 < MA50)"
            
            # RSI 14
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas[-14:]]
            losses = [-d if d < 0 else 0 for d in deltas[-14:]]
            avg_gain = sum(gains) / 14 if sum(gains) > 0 else 0.001
            avg_loss = sum(losses) / 14 if sum(losses) > 0 else 0.001
            rs = avg_gain / avg_loss
            rsi_14 = 100 - (100 / (1 + rs))
            
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
                macd_status = "Cắt lên Signal (MUA sớm)"
            elif hist > 0:
                macd_status = "Dương (Xung lực khỏe)"
            elif hist < 0 and prev_hist >= 0:
                macd_status = "Cắt xuống Signal (BÁN sớm)"
            else:
                macd_status = "Âm (Xung lực yếu)"

            # Bollinger Bands (20, 2)
            subset20 = closes[-20:]
            variance = sum((x - ma20)**2 for x in subset20) / 20
            std_dev = math.sqrt(variance)
            upper_bb = ma20 + 2 * std_dev
            lower_bb = ma20 - 2 * std_dev
            bandwidth = ((upper_bb - lower_bb) / ma20) * 100
            
            if bandwidth < 7.5:
                bb_status = "Nút thắt cổ chai (Sắp bùng nổ biến động)"
            elif latest_price >= upper_bb * 0.99:
                bb_status = "Chạm dải trên (Cản ngắn hạn)"
            elif latest_price <= lower_bb * 1.01:
                bb_status = "Chạm dải dưới (Hỗ trợ bắt đáy)"
            else:
                bb_status = "Dao động ổn định trong dải"

            # Kháng cự / Hỗ trợ kỹ thuật 20 phiên (Swing High / Swing Low)
            swing_res = max(highs[-20:]) if highs else ma20 * 1.05
            swing_sup = min(lows[-20:]) if lows else ma20 * 0.95

            # Mô hình nến phiên gần nhất (Price Action)
            o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
            body = abs(c - o)
            candle_range = h - l if (h - l) > 0 else 0.001
            lower_shadow = min(o, c) - l
            upper_shadow = h - max(o, c)
            
            if lower_shadow >= 1.8 * body and body > 0:
                candle_desc = "Rút chân mạnh (Cầu bắt đáy tốt)"
            elif upper_shadow >= 1.8 * body and body > 0:
                candle_desc = "Bị bán ép ngược (Cụt đầu)"
            elif c > o and (body / candle_range) >= 0.7:
                candle_desc = "Nến xanh đặc (Bên mua áp đảo)"
            elif c < o and (body / candle_range) >= 0.7:
                candle_desc = "Nến đỏ đặc (Bên bán chi phối)"
            elif (body / c) < 0.003:
                candle_desc = "Doji (Lưỡng lự giằng co)"
            else:
                candle_desc = "Biến động tích lũy thông thường"

            # Tỷ lệ khối lượng so với TB20 phiên
            latest_vol = volumes[-1]
            avg_vol_20 = sum(volumes[-20:]) / 20
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
            
            if vol_ratio >= 1.5:
                vol_eval = f"BÙNG NỔ ({vol_ratio:.1f}x TB20P)"
            elif vol_ratio >= 1.1:
                vol_eval = f"Tích cực ({vol_ratio:.1f}x TB20P)"
            elif vol_ratio <= 0.7:
                vol_eval = f"Cạn kiệt ({vol_ratio:.1f}x TB20P)"
            else:
                vol_eval = f"Cân bằng ({vol_ratio:.1f}x TB20P)"

            sector = SECTOR_MAP.get(ticker, "Khác")

            return {
                "ticker": ticker,
                "sector": sector,
                "price": latest_price,
                "change_pct": round(pct_change, 2),
                "rsi": round(rsi_14, 1),
                "ma20": round(ma20, 1),
                "ma50": round(ma50, 1),
                "trend_ma": trend_ma,
                "ma_cross": ma_cross,
                "macd_status": macd_status,
                "macd_hist": round(hist, 2),
                "bb_status": bb_status,
                "bandwidth": round(bandwidth, 1),
                "candle": candle_desc,
                "support": round(swing_sup, 0),
                "resistance": round(swing_res, 0),
                "vol_status": vol_eval,
                "vol_ratio": round(vol_ratio, 2)
            }
    except Exception as e:
        print(f"[!] Lỗi khi phân tích mã {ticker}: {e}")
        return None


# ================= 4. BỘ PHÂN TÍCH ĐỊNH LƯỢNG DỰ PHÒNG CHUYÊN SÂU =================
def generate_quantitative_briefing_pro(stock_summaries: list, vnindex: dict, intermarket: dict, news: list) -> str:
    """Tạo bản tin phân tích định lượng chuyên sâu dự phòng (khi toàn bộ API AI bị gián đoạn)"""
    sections = []
    
    # 1. Bối cảnh vĩ mô
    sections.append("🌐 *I. BỐI CẢNH VĨ MÔ & LIÊN THỊ TRƯỜNG:*")
    if intermarket:
        inter_items = [f"{k}: `{v['price']:,.2f}` ({v['pct']:+0.2f}%)" for k, v in intermarket.items()]
        sections.append("• *Chỉ số thế giới:* " + " | ".join(inter_items))
    if news:
        sections.append("• *Điểm tin sáng:*")
        for n in news[:2]:
            sections.append(f"  - {n}")

    # 2. VN-INDEX
    sections.append("\n📊 *II. XUNG LỰC THỊ TRƯỜNG CHUNG VN-INDEX:*")
    if vnindex:
        v_chg = vnindex['change_pct']
        icon_v = "🟢" if v_chg > 0 else "🔴"
        sections.append(f"• {icon_v} *{vnindex['name']}*: `{vnindex['close']:,.2f}` điểm ({v_chg:+0.2f}%) | Vol: {vnindex.get('vol_ratio', 1.0):.2f}x TB20P")
        sections.append(f"• Vị thế: *{vnindex.get('trend', 'Quan sát')}* | Hỗ trợ: `{vnindex.get('support', 0):,.0f}` | Kháng cự: `{vnindex.get('resistance', 0):,.0f}`")
    else:
        sections.append("• Thị trường phân hóa, dòng tiền thận trọng tích lũy.")

    # 3. Phân tích nhóm ngành
    sections.append("\n🎯 *III. BẢN ĐỒ DÒNG TIỀN THEO NHÓM NGÀNH:*")
    by_sector = {}
    for s in stock_summaries:
        by_sector.setdefault(s['sector'], []).append(s)

    for sec, stocks in by_sector.items():
        sections.append(f"\n📂 *Nhóm {sec}:*")
        for s in stocks:
            chg = s['change_pct']
            icon = "🟢" if chg > 0 else ("🔴" if chg < 0 else "🟡")
            sections.append(
                f"  {icon} *{s['ticker']}* (`{s['price']:,.0f}` đ, {chg:+0.2f}%): "
                f"RSI={s['rsi']} | {s['trend_ma']} | MACD: {s['macd_status']} | Nến: {s['candle']}"
            )

    # 4. Chiến lược khuyến nghị
    sections.append("\n🚀 *IV. CHIẾN LƯỢC HÀNH ĐỘNG HÔM NAY:*")
    bullish_stocks = [s for s in stock_summaries if "TRÊN" in s['trend_ma'] and 45 <= s['rsi'] <= 68 and s['macd_hist'] > 0]
    
    if bullish_stocks:
        top = bullish_stocks[0]
        buy_low = top['price'] * 0.985
        buy_high = top['price'] * 1.005
        target = top['resistance'] if top['resistance'] > top['price'] else top['price'] * 1.08
        stoploss = top['support'] * 0.98 if top['support'] < top['price'] else top['ma20'] * 0.96
        sections.append(f"• ⭐ *Cổ phiếu ưu tiên giải ngân:* *{top['ticker']}* ({top['sector']})")
        sections.append(f"  - Vùng canh mua an toàn: `{buy_low:,.0f} - {buy_high:,.0f} đ`")
        sections.append(f"  - Giá mục tiêu (Target): `{target:,.0f} đ`")
        sections.append(f"  - Ngưỡng dừng lỗ (Stoploss): `{stoploss:,.0f} đ`")
    else:
        squeeze_stocks = [s for s in stock_summaries if "Sắp bùng nổ" in s['bb_status']]
        if squeeze_stocks:
            sq = squeeze_stocks[0]
            sections.append(f"• ⏳ *Cổ phiếu tích lũy chặt chờ bùng nổ (Squeeze):* *{sq['ticker']}* - Canh mua thăm dò quanh MA20 (`{sq['ma20']:,.0f} đ`).")
        else:
            sections.append("• Tỷ trọng khuyến nghị: Duy trì 50% tiền mặt / 50% cổ phiếu, ưu tiên bảo toàn vốn.")

    sections.append("\n🛡️ *V. NGUYÊN TẮC QUẢN TRỊ DANH MỤC:*")
    sections.append("• Tuân thủ kỷ luật cắt lỗ tuyệt đối khi gãy hỗ trợ cứng (Stoploss).")
    sections.append("• Không mua đuổi khi RSI vượt 70, ưu tiên giải ngân ở các nhịp rũ bỏ kiểm định MA20.")
    sections.append("\n⚠️ _Báo cáo định lượng tự động xây dựng từ mô hình CMT (RSI, MACD, Bollinger Bands, MA20/50, Price Action)._")
    
    return "\n".join(sections)


# ================= 5. AI CHUYÊN GIA PHÂN TÍCH CHIẾN LƯỢC ĐẦU TƯ =================
def ask_gemini_pro(stock_summaries: list, vnindex: dict, intermarket: dict, news: list, api_key: str) -> str:
    """
    Gửi toàn bộ ma trận dữ liệu vào Google Gemini AI dưới persona:
    Giám đốc Khối Phân tích Chiến lược & Quản lý Danh mục (Chief Investment Officer & Head of Research)
    """
    # Soạn thảo bảng dữ liệu vĩ mô
    intermarket_lines = []
    if intermarket:
        for k, v in intermarket.items():
            intermarket_lines.append(f"- {k}: {v['price']:,.2f} ({v['pct']:+0.2f}%)")
    intermarket_str = "\n".join(intermarket_lines) if intermarket_lines else "Chưa có dữ liệu liên thị trường."

    # Soạn thảo tin tức
    news_str = "\n".join([f"- {n}" for n in news]) if news else "Không có tin tức đột biến."

    # Soạn thảo VN-INDEX
    if vnindex:
        vni_str = (
            f"Chỉ số: {vnindex['name']} = {vnindex['close']:,.2f} điểm ({vnindex['change_pct']:+0.2f}%)\n"
            f"- Trạng thái: {vnindex.get('trend')} | Thanh khoản: {vnindex.get('vol_ratio', 1.0)}x TB20 phiên\n"
            f"- Đường MA20: {vnindex.get('ma20'):,.2f} | MA50: {vnindex.get('ma50'):,.2f} | RSI: {vnindex.get('rsi')}\n"
            f"- Hỗ trợ 20 phiên: {vnindex.get('support'):,.2f} | Kháng cự 20 phiên: {vnindex.get('resistance'):,.2f}"
        )
    else:
        vni_str = "VN-INDEX: Đang trong vùng giằng co tích lũy phân hóa."

    # Soạn thảo dữ liệu từng mã cổ phiếu theo nhóm ngành
    stocks_lines = []
    for s in stock_summaries:
        stocks_lines.append(
            f"• [{s['sector']}] Mã {s['ticker']}: Giá {s['price']:,.0f} đ ({s['change_pct']:+0.2f}%) | "
            f"RSI={s['rsi']} | MA20={s['ma20']:,.0f} ({s['trend_ma']}, {s['ma_cross']}) | "
            f"MACD: {s['macd_status']} (Hist: {s['macd_hist']:+0.2f}) | "
            f"Bollinger: {s['bb_status']} (Bandwidth: {s['bandwidth']}%) | "
            f"Nến: {s['candle']} | Khối lượng: {s['vol_status']} | "
            f"Hỗ trợ: {s['support']:,.0f} đ | Kháng cự: {s['resistance']:,.0f} đ"
        )
    stocks_str = "\n".join(stocks_lines)

    prompt = f"""Bạn là Giám đốc Khối Phân tích Chiến lược & Quản lý Danh mục Đầu tư (Chief Investment Officer & Head of Research) tại một Công ty Chứng khoán hàng đầu Việt Nam.

DƯỚI ĐÂY LÀ TOÀN BỘ MA TRẬN DỮ LIỆU ĐẦU NGÀY:

=== BỐI CẢNH VĨ MÔ & LIÊN THỊ TRƯỜNG ===
{intermarket_str}

=== ĐIỂM TIN NÓNG BUỔI SÁNG ===
{news_str}

=== BỨC TRANH THỊ TRƯỜNG CHUNG VN-INDEX ===
{vni_str}

=== MA TRẬN KỸ THUẬT DANH MỤC CỔ PHIẾU THEO NHÓM NGÀNH ===
{stocks_str}

---
NHIỆM VỤ CỦA BẠN:
Hãy soạn thảo một BẢN TIN CHIẾN LƯỢC BUỔI SÁNG gửi các Nhà đầu tư chuyên nghiệp qua Telegram trước giờ mở cửa phiên (08:00 AM) với văn phong: SẮC BÉN, DỨT KHOÁT, THỰC CHIẾN, CHUẨN THUẬT NGỮ CHUYÊN GIA CHỨNG KHOÁN (không nói chung chung lý thuyết sáo rỗng).

CẤU TRÚC BẢN TIN BẮT BUỘC 5 PHẦN NHƯ SAU:

🌐 1. BỐI CẢNH VĨ MÔ & LIÊN THỊ TRƯỜNG:
- Tác động từ đêm qua (Phố Wall, DXY - áp lực tỷ giá, Giá Dầu, Vàng) đến tâm lý phiên ATO tại Việt Nam.
- Đánh giá nhanh 1-2 tin tức trong nước tác động đến dòng tiền.

📊 2. NHẬN ĐỊNH VN-INDEX & XU HƯỚNG DÒNG TIỀN:
- Đánh giá trạng thái VN-INDEX (đang trong pha nào: Tích lũy rũ bỏ, Giữ nền trên MA20, hay Điều chỉnh kiểm định hỗ trợ?).
- Kịch bản phiên hôm nay: Vùng hỗ trợ then chốt cần giữ vững và vùng cản cản trở đà tăng.

🎯 3. BẢN ĐỒ DÒNG TIỀN THEO NHÓM NGÀNH (SECTOR ROTATION):
- Phân tích ngắn gọn dòng tiền luân chuyển giữa các nhóm: Ngân hàng, Bán lẻ/Công nghệ, Thép, Chứng khoán, Bất động sản.
- Nhóm nào đang đóng vai trò dẫn dắt (Leader)? Nhóm nào chịu áp lực chốt lời/điều chỉnh?

🚀 4. CHIẾN LƯỢC HÀNH ĐỘNG & CỔ PHIẾU TÂM ĐIỂM HÔM NAY:
- ⭐ MÃ MUA TIỀM NĂNG (chọn 1-2 mã khỏe nhất có cấu trúc đẹp, MACD/RSI/Nến/Vol ủng hộ hoặc thắt nút Bollinger):
  * Ghi rõ: Mã cổ phiếu - Vùng canh mua cụ thể - Giá mục tiêu chốt lời (Target) - Ngưỡng dừng lỗ kỹ thuật (Stoploss).
- ⚠️ CẢNH BÁO RỦI RO / CHỐT LỜI: Mã nào chạm cản, RSI quá mua (>70) hoặc gãy MA20 cần hạ tỷ trọng?

🛡️ 5. PHÂN BỔ TỶ TRỌNG & KỶ LUẬT ĐI TIỀN:
- Tỷ trọng khuyến nghị cụ thể (% Cổ phiếu / % Tiền mặt).
- Lời khuyên tâm lý giao dịch phiên hôm nay (tránh FOMO ATO, nguyên tắc giải ngân từng phần).

Định dạng yêu cầu: Sử dụng icon emoji hợp lý, bullet point rõ ràng, giá tiền định dạng chuẩn (ví dụ 66.000 đ), dễ đọc lướt trên điện thoại trong 2 phút."""

    candidate_models = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-3.1-flash-lite",
        "gemma-4-26b-a4b-it",
    ]

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.45,
            "maxOutputTokens": 2048
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
                    if text_result and len(text_result.strip()) > 80:
                        print(f"[+] Model {clean_model} đã phân tích thành công!")
                        return text_result
            except urllib.error.HTTPError as e:
                print(f"[!] Model {clean_model} trả về HTTP {e.code}: {e.reason}")
                if e.code in (503, 429, 404):
                    print(f"    -> Đang tự động chuyển sang model dự phòng kế tiếp...")
                    time.sleep(1)
                    break
                time.sleep(2)
            except Exception as e:
                print(f"[!] Lỗi khi gọi model {clean_model}: {e}")
                time.sleep(1)

    print("[!] Toàn bộ AI API đều quá tải. Kích hoạt bộ phân tích định lượng chuyên sâu dự phòng...")
    return generate_quantitative_briefing_pro(stock_summaries, vnindex, intermarket, news)


# ================= 6. GIAO NHẬN TIN NHẮN AN TOÀN QUA TELEGRAM =================
def send_telegram(message: str, bot_token: str, chat_id: str):
    """Gửi bản tin chiến lược hoàn chỉnh về Telegram cá nhân an toàn với đa tầng Fallback"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    full_message = (
        f"☕ *BẢN TIN CHIẾN LƯỢC ĐẦU TƯ SÁNG {today_str}*\n"
        f"_Báo cáo Chiến lược & Định vị Dòng tiền chuyên sâu_\n\n"
        f"{message}"
    )

    # Chia nhỏ tin nhắn nếu vượt quá 3800 ký tự
    max_len = 3800
    parts = [full_message[i:i+max_len] for i in range(0, len(full_message), max_len)]

    for idx, part in enumerate(parts):
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
            with urllib.request.urlopen(req, timeout=12) as resp:
                print(f"[+] Đã gửi phần {idx+1}/{len(parts)} về Telegram thành công!")
        except urllib.error.HTTPError as e:
            print(f"[!] Gửi Markdown thất bại ({e.code}). Chuyển sang chế độ Plaintext...")
            # Fallback gửi Plaintext nếu Markdown lỗi ký tự
            payload.pop("parse_mode", None)
            req2 = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'content-type': 'application/json'}
            )
            try:
                with urllib.request.urlopen(req2, timeout=12):
                    print(f"[+] Đã gửi phần {idx+1}/{len(parts)} về Telegram (Plaintext) thành công!")
            except Exception as ex:
                print(f"[!] Lỗi khi gửi Telegram Plaintext: {ex}")


# ================= 7. ĐIỀU PHỐI TOÀN BỘ LUỒNG PIPELINE =================
def run_pipeline():
    start_time = time.time()
    print("=" * 70)
    print("🚀 BẮT ĐẦU CHẠY HỆ THỐNG PHÂN TÍCH CHIẾN LƯỢC CHỨNG KHOÁN VIỆT NAM")
    print(f"⏰ Thời gian kích hoạt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. Thu thập liên thị trường & Tin tức vĩ mô
    print("\n[*] 1/4. Đang thu thập chỉ số liên thị trường & tin tức vĩ mô...")
    intermarket = fetch_intermarket_pulse()
    news = fetch_macro_news()
    print(f"    -> Đã lấy {len(intermarket)} chỉ số thế giới và {len(news)} tin tức sáng sớm.")

    # 2. Thu thập dữ liệu chỉ số VN-INDEX
    print("\n[*] 2/4. Đang thu thập và phân tích chỉ số chung VN-INDEX...")
    vnindex = fetch_vnindex_summary()
    if vnindex:
        print(f"    -> VN-INDEX: {vnindex['close']:,.2f} điểm ({vnindex['change_pct']:+0.2f}%), {vnindex.get('trend')}")
    else:
        print("    -> Không lấy được chỉ số VN-INDEX. Sẽ sử dụng phân tích độ rộng cổ phiếu.")

    # 3. Thu thập và phân tích danh mục cổ phiếu đa luồng
    print(f"\n[*] 3/4. Đang phân tích kỹ thuật đa chiều cho danh mục ({', '.join(WATCHLIST)})...")
    stock_summaries = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_stock_data_pro, WATCHLIST))

    for res in results:
        if res:
            stock_summaries.append(res)
            print(
                f"    -> {res['ticker']:4s} [{res['sector']:11s}]: "
                f"Giá {res['price']:>8,.0f} đ ({res['change_pct']:+5.2f}%) | "
                f"RSI: {res['rsi']:4.1f} | MACD: {res['macd_status']:20s} | "
                f"BB: {res['bb_status']:25s} | Vol: {res['vol_status']}"
            )

    if not stock_summaries:
        print("[!] Không thu thập được dữ liệu kỹ thuật của cổ phiếu nào. Kết thúc luồng.")
        return

    # 4. Phân tích chiến lược qua AI Senior Equity Analyst
    print("\n[*] 4/4. Đang gửi toàn bộ dữ liệu ma trận cho Gemini AI phân tích chuyên sâu...")
    if not GEMINI_API_KEY:
        print("[!] Chưa cấu hình GEMINI_API_KEY. Kích hoạt bộ phân tích định lượng...")
        briefing = generate_quantitative_briefing_pro(stock_summaries, vnindex, intermarket, news)
    else:
        briefing = ask_gemini_pro(stock_summaries, vnindex, intermarket, news, GEMINI_API_KEY)

    # 5. Gửi bản tin về Telegram
    print("\n[*] Đang gửi bản tin chiến lược hoàn chỉnh về Telegram cá nhân...")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram(briefing, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    else:
        print("[!] Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")

    elapsed = time.time() - start_time
    print(f"\n🎉 HOÀN THÀNH TOÀN BỘ BẢN TIN BUỔI SÁNG TRONG {elapsed:.1f} GIÂY!")
    print("=" * 70)


if __name__ == "__main__":
    run_pipeline()
