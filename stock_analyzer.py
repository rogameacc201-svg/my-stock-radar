import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import datetime
import time

st.set_page_config(page_title="台股量化選股雷達", layout="wide")

# ==========================================
# 強化版：自動回溯前一個交易日
# ==========================================
def get_top_50_stocks():
    # 嘗試往回推 7 天，找尋有成交量的日期
    for i in range(7):
        target_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        
        # 使用 FinMind 抓取歷史日收盤資料
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockPrice", "start_date": target_date, "end_date": target_date}
        try:
            res = requests.get(url, params=params, timeout=10)
            data = res.json().get('data', [])
            if data and len(data) > 50: # 確保有資料
                df = pd.DataFrame(data)
                df = df[(df['stock_id'].str.len() == 4) & (df['stock_id'].str.isdigit())]
                df['Trading_Volume'] = pd.to_numeric(df['Trading_Volume'], errors='coerce')
                df_top50 = df.sort_values(by='Trading_Volume', ascending=False).head(50)
                st.sidebar.success(f"✅ 成功抓取 {target_date} 的熱門交易數據！")
                return dict(zip(df_top50['stock_id'], df_top50['stock_id']))
        except:
            continue
    return {"2330": "台積電", "2317": "鴻海", "2454": "聯發科"} # 真的抓不到才給保底

# ==========================================
# 網頁控制
# ==========================================
st.sidebar.header("設定")
mode = st.sidebar.radio("來源：", ("🔥 自動抓取最近交易日成交量前 50 大", "✍️ 自訂"))

if mode == "🔥 自動抓取最近交易日成交量前 50 大":
    stock_pool = get_top_50_stocks()
else:
    user_input = st.sidebar.text_input("輸入代碼 (逗號隔開)", "2330,2317")
    stock_pool = {s.strip(): s.strip() for s in user_input.split(',')}

# ==========================================
# 掃描與執行 (保持簡潔)
# ==========================================
st.title("🏆 台股量化爭霸榜")
if st.button("🚀 開始分析"):
    results = []
    # 為了演示，我們只跑前 10 檔，避免你等太久
    target_list = list(stock_pool.items())[:10] 
    
    for s_id, s_name in target_list:
        try:
            ticker = yf.Ticker(f"{s_id}.TW")
            info = ticker.info
            name = info.get('shortName', s_name)
            price = info.get('currentPrice', 0)
            results.append({"代號": s_id, "名稱": name, "股價": price})
        except:
            continue
            
    st.table(pd.DataFrame(results))
