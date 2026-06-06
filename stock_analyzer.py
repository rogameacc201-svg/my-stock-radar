import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import datetime
import time

# 網頁基本設定
st.set_page_config(page_title="台股量化多因子選股雷達", page_icon="📈", layout="wide")

# ==========================================
# 側邊欄控制面板
# ==========================================
st.sidebar.header("⚙️ 雷達核心設定")
mode = st.sidebar.radio(
    "選擇選股池來源：",
    ("🔥 全台股成交量前 50 大 (真正動態抓取)", "✍️ 自訂股票代碼 (手動輸入)")
)

stock_pool = {}

if mode == "🔥 全台股成交量前 50 大 (真正動態抓取)":
    st.sidebar.info("📊 系統正透過雙管道自動撈取最新交易日成交量前 50 檔正股。")
    
    @st.cache_data(ttl=1800)
    def fetch_real_twse_top_50():
        # 管道 A：FinMind API
        try:
            three_days_ago = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
            res = requests.get("https://api.finmindtrade.com/api/v4/data", 
                               params={"dataset": "TaiwanStockPrice", "start_date": three_days_ago}, timeout=10)
            if res.status_code == 200:
                data = res.json().get('data', [])
                if data:
                    df = pd.DataFrame(data)
                    latest_date = df['date'].max()
                    df = df[df['date'] == latest_date]
                    df = df[(df['stock_id'].str.len() == 4) & (df['stock_id'].str.isdigit())]
                    df['Trading_Volume'] = pd.to_numeric(df['Trading_Volume'], errors='coerce')
                    df_top50 = df.sort_values(by='Trading_Volume', ascending=False).head(50)
                    return dict(zip(df_top50['stock_id'], df_top50['stock_id']))
        except: pass
        
        # 管道 B：證交所官方備援
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            for i in range(5):
                date_str = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y%m%d")
                url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALL"
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200 and res.text.strip().startswith("{"):
                    data = res.json()
                    if 'data9' in data:
                        df = pd.DataFrame(data['data9'])
                        df = df[(df[0].str.len() == 4) & (df[0].str.isdigit())]
                        df[2] = pd.to_numeric(df[2].str.replace(',', ''), errors='coerce')
                        df_top50 = df.sort_values(by=2, ascending=False).head(50)
                        return dict(zip(df_top50[0], df_top50[1]))
        except: pass
        
        return {"2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達", "3231": "緯創"}
            
    stock_pool = fetch_real_twse_top_50()
else:
    user_input = st.sidebar.text_area("請輸入股票代碼 (逗號隔開)：", value="2330, 2317, 2454, 2603")
    for s_id in user_input.split(','):
        if s_id.strip().isdigit(): stock_pool[s_id.strip()] = f"個股 {s_id.strip()}"

# ==========================================
# 核心計算與打分
# ==========================================
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

def calculate_stock_score(stock_id, default_name):
    yf_symbol = f"{stock_id}.TW"
    ticker = yf.Ticker(yf_symbol)
    total_score = 0
    close_price_str, latest_yoy_str, trend_desc = "N/A", "N/A", "震盪"
    actual_name = default_name
    
    # 1. 技術量能
    try:
        df = ticker.history(period="6mo")
        if not df.empty:
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA60'] = df['Close'].rolling(60).mean()
            latest = df.iloc[-1]
            close_price_str = f"{latest['Close']:.1f}"
            if latest['Close'] > latest['MA20'] > latest['MA60']: total_score += 15
    except: pass

    # 2. 營收 YoY
    try:
        res = requests.get(FINMIND_URL, params={"dataset": "TaiwanStockMonthRevenue", "data_id": stock_id, "start_date": "2024-01-01"}, timeout=5)
        df_rev = pd.DataFrame(res.json().get('data', []))
        if not df_rev.empty:
            yoy = (float(df_rev.iloc[-1]['revenue']) / float(df_rev.iloc[-13]['revenue']) - 1) * 100
            latest_yoy_str = f"{yoy:+.1f}%"
            if yoy > 10: total_score += 10
    except: pass

    # 3. 財報獲利 + 名稱校正
    try:
        info = ticker.info
        if "個股" in default_name or default_name == stock_id:
            actual_name = info.get('shortName', default_name).replace("CO.,LTD.", "").strip()
        if info.get('returnOnEquity', 0) > 0.15: total_score += 15
    except: pass

    return {"代號": stock_id, "股名": actual_name, "綜合總分": total_score, "最新股價": close_price_str, "營收YoY": latest_yoy_str, "技術型態": trend_desc}

# ==========================================
# 網頁視覺
# ==========================================
st.title("🏆 今日台股量化多因子選股雷達")
if st.button("🚀 啟動雷達掃描"):
    results = []
    progress = st.progress(0)
    for i, (s_id, s_name) in enumerate(stock_pool.items()):
        results.append(calculate_stock_score(s_id, s_name))
        progress.progress((i + 1) / len(stock_pool))
    
    df_result = pd.DataFrame(results).sort_values(by="綜合總分", ascending=False)
    st.success("掃描完成！")
    st.dataframe(df_result, use_container_width=True)
