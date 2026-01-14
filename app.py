import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import google.generativeai as genai
import finnhub
from datetime import datetime, timedelta
import time

# --- 頁面設定 ---
st.set_page_config(page_title="AI 投資分析 Pro", layout="wide")

# --- 讀取 API Keys ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    FINNHUB_API_KEY = st.secrets["FINNHUB_API_KEY"]
except:
    st.error("請在 Streamlit 設定中輸入 API Keys")
    st.stop()

# 初始化 API
genai.configure(api_key=GEMINI_API_KEY)
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

# --- 核心函數 ---

def get_asset_type(ticker):
    if ticker.endswith('.TW') or ticker.endswith('.TWO'):
        return "Taiwan Stock"
    elif ticker in ['GC=F', 'GLD', 'SI=F', 'CL=F', 'BTC-USD']:
        return "Commodity/Crypto"
    else:
        return "US Stock/Global"

def get_realtime_data(ticker):
    """獲取即時價格、漲跌幅與 RSI"""
    try:
        stock = yf.Ticker(ticker)
        
        # 1. 獲取即時價格資訊
        price = stock.fast_info.last_price
        prev_close = stock.fast_info.previous_close
        
        # 計算漲跌
        change_amount = price - prev_close
        change_pct = (change_amount / prev_close) * 100
        currency = stock.info.get('currency', 'USD')

        # 2. 獲取歷史數據算 RSI
        hist = stock.history(period="3mo", auto_adjust=True)
        if hist.empty: return None, "找不到數據"
        
        # RSI 計算
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        return {
            "price": price,
            "change_amount": change_amount,
            "change_pct": change_pct,
            "rsi": current_rsi,
            "currency": currency
        }, None
    except Exception as e:
        return None, str(e)

def get_market_news(ticker):
    try:
        if ticker.endswith('.TW') or ticker == 'GC=F':
             return "無特定國際新聞，請專注於技術面與宏觀經濟分析。"
        
        today = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        news = finnhub_client.company_news(ticker, _from=week_ago, to=today)
        formatted = [f"- {n['headline']}" for n in news[:3]]
        return "\n".join(formatted) if formatted else "近期無重大新聞。"
    except:
        return "無法取得新聞。"

def ask_gemini(ticker, data, news, asset_type):
    # 定義模型優先順序：優先用最強的 Pro，失敗則降級用 Flash
    model_priority = [
        "models/gemini-3-pro-preview", 
        "models/gemini-2.5-flash"
    ]
    
    role = "華爾街經理人"
    if asset_type == "Taiwan Stock": role = "台股資深分析師 (熟悉外資與台幣匯率)"
    if asset_type == "Commodity/Crypto": role = "大宗商品與加密貨幣專家"

    prompt = f"""
    你是 {role}。請用繁體中文分析 {ticker}。
    
    【即時數據】
    - 現價：{data['price']:.2f} {data['currency']}
    - 漲跌：{data['change_amount']:.2f} ({data['change_pct']:.2f}%)
    - RSI指標：{data['rsi']:.2f}
    
    【近期新聞】
    {news}
    
    請以手機易讀的格式簡潔回答：
    1. **盤勢判讀**：今日漲跌的意義？趨勢是強勢還是疲弱？
    2. **技術風險**：RSI ({data['rsi']:.2f}) 是否過熱或背離？
    3. **操作建議**：積極者與保守者的操作區間。
    """

    # 嘗試呼叫模型
    for model_name in model_priority:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            print(f"⚠️ 模型 {model_name} 呼叫失敗: {e}")
            print("正在嘗試切換到下一個備用模型...")
            time.sleep(1)
            continue 

    return "❌ 系統忙碌中：所有 AI 模型目前皆無法回應，請稍後再試。"

# --- App 介面 ---

# 1. 處理網址參數
query_params = st.query_params
default_ticker = query_params.get("ticker", "2330.TW")

st.title("📈 Bruce AI 投資分析 (Pro)")

# [新增] 極簡潔的支援格式說明 (使用 st.caption)
st.caption("👉 支援格式：台股 (2330.TW) | 美股 (NVDA) | 加密貨幣 (BTC-USD) | 黃金 (GC=F)")

# 2. 輸入區塊 (Form)
with st.form("input_form"):
    col_input, col_btn = st.columns([3, 1])
    
    with col_input:
        ticker = st.text_input("輸入代號", value=default_ticker, label_visibility="collapsed", placeholder="輸入代號，如: 2330.TW")
    
    with col_btn:
        submitted = st.form_submit_button("開始分析", use_container_width=True)

# 3. 分享連結：使用 HTML/JS 隱藏網址，只顯示複製按鈕
ticker_clean = ticker.upper().strip()
app_base_url = "https://my-ai-stock-sgrnyzjr6fpoqxllbz7sbu.streamlit.app"
share_link = f"{app_base_url}/?ticker={ticker_clean}"

components.html(
    f"""
    <html>
        <body>
            <div style="display: flex; align-items: center; gap: 10px;">
                <button onclick="copyToClipboard()" style="
                    background-color: white; 
                    color: #31333F; 
                    border: 1px solid #d6d6d8; 
                    padding: 8px 12px; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    font-family: 'Source Sans Pro', sans-serif;
                    font-size: 14px;
                    display: flex;
                    align-items: center;
                    transition: all 0.2s;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
                " onmouseover="this.style.borderColor='#ff4b4b'; this.style.color='#ff4b4b'" 
                  onmouseout="this.style.borderColor='#d6d6d8'; this.style.color='#31333F'">
                    📋 複製分享連結
                </button>
                <span id="status" style="font-family: sans-serif; font-size: 12px; color: green; display: none; opacity: 0; transition: opacity 0.5s;">
                    ✅ 已複製！
                </span>
            </div>

            <script>
                function copyToClipboard() {{
                    const str = "{share_link}";
                    const el = document.createElement('textarea');
                    el.value = str;
                    el.setAttribute('readonly', '');
                    el.style.position = 'absolute';
                    el.style.left = '-9999px';
                    document.body.appendChild(el);
                    el.select();
                    document.execCommand('copy');
                    document.body.removeChild(el);
                    
                    const status = document.getElementById('status');
                    status.style.display = 'inline';
                    status.style.opacity = '1';
                    
                    setTimeout(function() {{
                        status.style.opacity = '0';
                        setTimeout(function() {{
                            status.style.display = 'none';
                        }}, 500);
                    }}, 2000);
                }}
            </script>
        </body>
    </html>
    """,
    height=50
)

# 4. 執行分析邏輯
if submitted:
    st.query_params["ticker"] = ticker_clean
    
    with st.spinner(f"正在連線交易所抓取 {ticker_clean} 數據..."):
        asset_type = get_asset_type(ticker_clean)
        data, error = get_realtime_data(ticker_clean)
        
        if error:
            st.error(f"發生錯誤: {error}")
        else:
            # 顯示即時看板
            st.markdown(f"### {ticker_clean} 即時看板")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    label="目前價格", 
                    value=f"{data['price']:.2f} {data['currency']}",
                    delta=f"{data['change_amount']:.2f} ({data['change_pct']:.2f}%)"
                )
            with col2:
                rsi_val = data['rsi']
                st.metric(label="RSI 強弱", value=f"{rsi_val:.2f}")
            with col3:
                 st.metric(label="資產類別", value=asset_type)

            st.markdown("---")

            # 呼叫 AI
            with st.spinner(f"正在閱讀新聞並進行 AI 分析..."):
                news = get_market_news(ticker_clean)
                analysis = ask_gemini(ticker_clean, data, news, asset_type)
            
                st.subheader("🤖 AI 分析觀點")
                st.markdown(analysis)
