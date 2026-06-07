import streamlit as st
import pandas as pd
import requests
import yfinance as yf

st.set_page_config(page_title="台股量化選股雷達", layout="wide")

# ==========================================
# 核心資料處理
# ==========================================
def fetch_top_50():
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date=20260605&type=ALL"
    try:
        df = pd.read_csv(url, header=1, thousands=',', encoding='cp950')
        df = df[df['證券代號'].astype(str).str.len() == 4]
        df = df.sort_values(by='成交股數', ascending=False).head(50)
        return dict(zip(df['證券代號'].astype(str), df['證券名稱']))
    except: return {}

# ==========================================
# 打分邏輯 (核心)
# ==========================================
def analyze_stock(s_id):
    ticker = yf.Ticker(f"{s_id}.TW")
    hist = ticker.history(period="1mo")
    info = ticker.info
    
    score = 0
    # 簡單技術指標：收盤 > 20MA 加分
    if not hist.empty:
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        if hist['Close'].iloc[-1] > ma20: score += 10
    
    # 基本面：ROE > 10% 加分
    if info.get('returnOnEquity', 0) > 0.1: score += 10
    
    return {
        "代號": s_id, 
        "名稱": info.get('shortName', '未知'),
        "目前總分": score,
        "最新股價": info.get('currentPrice', 0)
    }

# ==========================================
# 介面
# ==========================================
st.title("🏆 台股量化選股雷達")
mode = st.sidebar.radio("模式：", ("🔥 自動抓取前 50 大", "✍️ 自訂輸入"))

stock_pool = {}
if mode == "🔥 自動抓取前 50 大":
    stock_pool = fetch_top_50()
else:
    user_input = st.sidebar.text_input("輸入代號 (逗號隔開)", "2330, 2317")
    if user_input:
        for s in user_input.split(','):
            if s.strip().isdigit(): stock_pool[s.strip()] = "自訂標的"

if stock_pool and st.sidebar.button("開始分析"):
    results = []
    progress = st.progress(0)
    for i, s_id in enumerate(stock_pool.keys()):
        results.append(analyze_stock(s_id))
        progress.progress((i+1)/len(stock_pool))
    
    df_result = pd.DataFrame(results)
    st.dataframe(df_result.sort_values("目前總分", ascending=False), use_container_width=True)
else:
    st.info("請在左側載入資料或輸入代碼後，點擊「開始分析」。")
