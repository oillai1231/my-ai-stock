import streamlit as st
import yfinance as yf
import google.generativeai as genai
import finnhub
from datetime import datetime, timedelta

# --- 頁面設定 ---
st.set_page_config(page_title="AI 投資分析 Pro", layout="wide")

# --- 讀取 API Keys (從 Streamlit Secrets) ---
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
    """
    獲取即時價格、漲跌幅與 RSI
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. 獲取即時價格資訊 (盤中數據)
        # fast_info 通常比 history 更即時且包含昨收資訊
        price = stock.fast_info.last_price
        prev_close = stock.fast_info.previous_close
        
        # 計算漲跌
        change_amount = price - prev_close
        change_pct = (change_amount / prev_close) * 100
        currency = stock.info.get('currency', 'USD')

        # 2. 獲取歷史數據算 RSI (不需太即時，用最近收盤價即可)
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

import time

def ask_gemini(ticker, data, news, asset_type):
    # 定義我們的模型優先順序
    # 第一順位：最強大腦 (Gemini 3 Pro Preview) - 額度少，容易爆
    # 第二順位：速度王者 (Gemini 2.5 Flash) - 額度多，很難爆
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

    # 開始嘗試呼叫模型
    for model_name in model_priority:
        try:
            # 嘗試建立並呼叫當前模型
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            
            # 如果成功，回傳結果並跳出迴圈
            # (可以在這裡加個標記告訴使用者是用哪個模型，非必要)
            return response.text
            
        except Exception as e:
            # 如果失敗 (例如 ResourceExhausted)，印出錯誤但不要當機
            print(f"⚠️ 模型 {model_name} 呼叫失敗: {e}")
            print("正在嘗試切換到下一個備用模型...")
            time.sleep(1) # 稍微休息一下再試下一個
            continue # 繼續迴圈嘗試下一個模型

    # 如果所有模型都失敗了
    return "❌ 系統忙碌中：所有 AI 模型目前皆無法回應，請稍後再試。"

# --- App 介面 ---

# [修改點] 1. 處理網址參數 (分享功能的核心)
# 如果網址有 ?ticker=2330.TW，就抓出來當預設值，否則預設 2330.TW
query_params = st.query_params
default_ticker = query_params.get("ticker", "2330.TW")

st.title("📈 Bruce AI 投資分析 (Pro)")

# 側邊欄說明
with st.sidebar:
    st.write("目前使用模型：")
    st.info("Gemini 3 Flash ⚡")
    st.markdown("---")
    st.write("分享功能：")
    st.caption("分析完成後，複製瀏覽器網址即可分享當前結果給朋友。")

# 輸入區塊
with st.form("input_form"):
    ticker = st.text_input("輸入代號 (如 2330.TW, NVDA, BTC-USD)", value=default_ticker)
    submitted = st.form_submit_button("開始分析")

# 邏輯處理
if submitted:
    ticker = ticker.upper().strip()
    
    # [修改點] 2. 更新網址參數，讓使用者可以複製網址分享
    st.query_params["ticker"] = ticker
    
    with st.spinner(f"正在連線交易所與 AI 模型分析 {ticker}..."):
        asset_type = get_asset_type(ticker)
        data, error = get_realtime_data(ticker)
        
        if error:
            st.error(f"發生錯誤: {error}")
        else:
            news = get_market_news(ticker)
            analysis = ask_gemini(ticker, data, news, asset_type)
            
            # [修改點] 3. 顯示即時股價與漲跌幅 (使用 st.metric)
            st.markdown(f"### {ticker} 即時看板")
            
            # 建立三欄資訊
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    label="目前價格", 
                    value=f"{data['price']:.2f} {data['currency']}",
                    delta=f"{data['change_amount']:.2f} ({data['change_pct']:.2f}%)"
                )
            
            with col2:
                # RSI 根據數值給予簡單的顏色提示 (非標準 metric，用文字呈現)
                rsi_val = data['rsi']
                rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "off"
                st.metric(label="RSI 強弱指標", value=f"{rsi_val:.2f}")

            with col3:
                 st.metric(label="資產類別", value=asset_type)

            st.markdown("---")
            st.subheader("🤖 Gemini 3 觀點")
            st.markdown(analysis)
            
            # 額外顯示一個分享連結按鈕 (方便手機複製)
            # 這裡我們手動組合成完整網址顯示出來

            st.markdown("---")
            st.caption("🔗 分享此分析結果：")
            
            # [修改點] 請將下方的網址換成您瀏覽器上方真正的 App 網址
            # 例如改成: "https://my-ai-stock-sgrnyzjr6fpoqxllbz7sbu.streamlit.app/"
            app_base_url = "https://my-ai-stock-sgrnyzjr6fpoqxllbz7sbu.streamlit.app" 
            
            # 組合完整的分享連結
            share_link = f"{app_base_url}/?ticker={ticker}"
            
            st.code(share_link, language="text")

# --- 暫時加入這段來檢查可用模型 ---
with st.expander("🛠️ 開發者工具：檢查可用模型"):
    if st.button("列出所有 Gemini 模型"):
        try:
            st.write("正在查詢 API 權限...")
            models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    models.append(m.name)
            st.write("您的 API Key 可用的模型如下：")
            st.json(models) # 會以列表清楚顯示
        except Exception as e:
            st.error(f"查詢失敗: {e}")
# --------------------------------






