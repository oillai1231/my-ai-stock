import streamlit as st
import yfinance as yf
import google.generativeai as genai
import finnhub
from datetime import datetime, timedelta

# --- 頁面設定 ---
st.set_page_config(page_title="AI 投資分析", layout="mobile") # layout="mobile" 讓手機版更好看

# --- 讀取 API Keys (從 Streamlit Secrets) ---
# 我們稍後會在網頁後台設定這些密碼，避免直接寫在程式碼裡
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
    elif ticker in ['GC=F', 'GLD', 'SI=F', 'CL=F']:
        return "Commodity"
    else:
        return "US Stock/Global"

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo", auto_adjust=True)
        if hist.empty: return None, "找不到數據"
        
        current_price = hist['Close'].iloc[-1]
        
        # RSI 計算
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        currency = stock.info.get('currency', 'USD')
        return {"price": current_price, "rsi": current_rsi, "currency": currency}, None
    except Exception as e:
        return None, str(e)

def get_market_news(ticker):
    try:
        if ticker.endswith('.TW') or ticker == 'GC=F':
             # 台股/黃金若無特定新聞，回傳簡短提示
             return "無特定國際新聞，請專注於技術面與宏觀經濟分析。"
        
        today = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        news = finnhub_client.company_news(ticker, _from=week_ago, to=today)
        formatted = [f"- {n['headline']}" for n in news[:3]]
        return "\n".join(formatted) if formatted else "近期無重大新聞。"
    except:
        return "無法取得新聞。"

def ask_gemini(ticker, data, news, asset_type):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    role = "華爾街經理人"
    if asset_type == "Taiwan Stock": role = "台股資深分析師 (熟悉外資與台幣匯率)"
    if asset_type == "Commodity": role = "大宗商品專家 (關注通膨與美元)"

    prompt = f"""
    你是 {role}。請用繁體中文分析 {ticker}。
    數據：價格 {data['price']:.2f}, RSI {data['rsi']:.2f}。
    新聞：{news}
    請簡潔回答(手機版面閱讀)：
    1. **趨勢**：看多/看空/盤整？
    2. **風險**：RSI是否過熱？有何隱憂？
    3. **建議**：買進/賣出/觀望？(附理由)
    """
    response = model.generate_content(prompt)
    return response.text

# --- App 介面 ---
st.title("📈 AI 掌上投資顧問")

with st.form("input_form"):
    ticker = st.text_input("輸入代號 (如 2330.TW, NVDA, GC=F)", value="2330.TW")
    submitted = st.form_submit_button("開始分析")

if submitted:
    ticker = ticker.upper().strip()
    with st.spinner(f"正在分析 {ticker}..."):
        asset_type = get_asset_type(ticker)
        data, error = get_stock_data(ticker)
        
        if error:
            st.error(f"發生錯誤: {error}")
        else:
            news = get_market_news(ticker)
            analysis = ask_gemini(ticker, data, news, asset_type)
            
            # 顯示結果
            st.markdown(f"### {ticker} 分析報告")
            col1, col2 = st.columns(2)
            col1.metric("價格", f"{data['price']:.2f} {data['currency']}")
            col2.metric("RSI 強弱", f"{data['rsi']:.2f}")
            st.markdown("---")
            st.markdown(analysis)