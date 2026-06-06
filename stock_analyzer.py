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
    st.sidebar.info("📊 系統正透過雙管道機制（FinMind API / TWSE）自動撈取最新一個交易日全市場成交量前 50 檔正股。")
    
    @st.cache_data(ttl=1800)  # 緩存 30 分鐘
    def fetch_real_twse_top_50():
        # 管道 A：優先嘗試 FinMind 穩定管道 (專為週末與高頻率存取設計)
        try:
            # 取得 3 天前的日期，確保能涵蓋到最新的交易日
            three_days_ago = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
            url = "https://api.finmindtrade.com/api/v4/data"
            # 抓取全市場日成交行情
            params = {"dataset": "TaiwanStockPriceTick", "start_date": three_days_ago}
            
            # 如果一般 Tick 資料庫週末維護，改抓常規日收盤
            res = requests.get(url, params={"dataset": "TaiwanStockPrice", "start_date": three_days_ago}, timeout=10)
            if res.status_code == 200:
                data = res.json().get('data', [])
                if data:
                    df_fm = pd.DataFrame(data)
                    # 篩選最新一天的資料
                    latest_date = df_fm['date'].max()
                    df_fm = df_fm[df_fm['date'] == latest_date]
                    
                    # 過濾純 4 位數台股正股
                    df_fm = df_fm[df_fm['stock_id'].str.len() == 4]
                    df_fm = df_fm[df_fm['stock_id'].str.isdigit()]
                    
                    # 依成交量（Trading_Volume）排序
                    df_fm['Trading_Volume'] = pd.to_numeric(df_fm['Trading_Volume'], errors='coerce')
                    df_top50 = df_fm.sort_values(by='Trading_Volume', ascending=False).head(50)
                    
                    # 由於 FinMind 預設不一定帶中文名，我們建立代碼清單，隨後大腦會自動去 Yahoo 正名
                    return dict(zip(df_top50['stock_id'], df_top50['stock_id']))
        except:
            pass # 如果管道 A 失敗，無縫滑入管道 B

        # 管道 B：證交所官方網頁備援機制
        try:
            target_date = datetime.datetime.now()
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            for _ in range(5):
                date_str = target_date.strftime("%Y%m%d")
                url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALL"
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200 and res.text.strip().startswith("{"):
                    data = res.json()
                    if 'data9' in data:
                        df_all = pd.DataFrame(data['data9'])
                        df_all[0] = df_all[0].str.strip()
                        df_all[1] = df_all[1].str.strip()
                        df_all = df_all[(df_all[0].str.len() == 4) & (df_all[0].str.isdigit())]
                        df_all[2] = df_all[2].str.replace(',', '')
                        df_all[2] = pd.to_numeric(df_all[2], errors='coerce')
                        df_top50 = df_all.sort_values(by=2, ascending=False).head(50)
                        return dict(zip(df_top50[0], df_top50[1]))
                target_date -= datetime.timedelta(days=1)
        except:
            pass

        # 終極保底：萬一兩大外網在週末同時大斷線，才吐出這 12 檔
        return {
            "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達", 
            "3231": "緯創", "2603": "長榮", "2609": "陽明", "2615": "萬海",
            "2308": "台達電", "2357": "華碩", "2881": "富邦金", "2882": "國泰金"
        }
            
    stock_pool = fetch_real_twse_top_50()

else:
    user_input = st.sidebar.text_area(
        "請輸入股票代碼（多檔請用英文逗號隔開）：", 
        value="2330, 2317, 2454, 2603, 2882"
    )
    for s_id in user_input.split(','):
        s_id = s_id.strip()
        if s_id.isdigit():
            stock_pool[s_id] = f"個股 {s_id}"

# ==========================================
# 初始化全域數據（美股、總經）
# ==========================================
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
two_weeks_ago = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
two_months_ago = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")

@st.cache_data(ttl=3600)
def fetch_global_metrics():
    try:
        us_df = yf.Ticker("^SOX").history(period="3mo")
        us_df['MA_20'] = us_df['Close'].rolling(window=20).mean()
        us_bullish = us_df.iloc[-1]['Close'] > us_df.iloc[-1]['MA_20']
        
        res_fx = requests.get(FINMIND_URL, params={"dataset": "TaiwanExchangeRate", "data_id": "USD", "start_date": two_months_ago}, timeout=10)
        df_fx = pd.DataFrame(res_fx.json()['data'])
        fx_bullish = df_fx.iloc[-1]['exchange_rate_buy'] > df_fx.iloc[-20]['exchange_rate_buy']
        
        res_macro = requests.get(FINMIND_URL, params={"dataset": "TaiwanMacroEconomic", "data_id": "ExportOrders", "start_date": "2025-01-01"}, timeout=10)
        macro_growth = float(pd.DataFrame(res_macro.json()['data']).iloc[-1]['comparison_with_last_year']) > 0
        return us_bullish, fx_bullish, macro_growth
    except:
        return True, True, True

us_bullish, fx_bullish, macro_growth = fetch_global_metrics()

# ==========================================
# 核心十一因子打分大腦 (新增自動正名功能)
# ==========================================
def calculate_stock_score(stock_id, default_name):
    yf_symbol = f"{stock_id}.TW"
    ticker = yf.Ticker(yf_symbol)
    total_score = 0
    close_price_str, latest_yoy_str, trend_desc = "N/A", "N/A", "震盪整理"
    actual_name = default_name
    
    # 1. 技術量能
    try:
        df_price = ticker.history(period="6mo")
        if not df_price.empty:
            df_price['MA_20'] = df_price['Close'].rolling(window=20).mean()
            df_price['MA_60'] = df_price['Close'].rolling(window=60).mean()
            df_price['MA_5'] = df_price['Close'].rolling(window=5).mean()
            df_price['Vol_MA5'] = df_price['Volume'].rolling(window=5).mean()
            
            latest = df_price.iloc[-1]
            close = latest['Close']
            close_price_str = f"{close:.1f}"
            
            if close > latest['MA_20'] and latest['MA_20'] > latest['MA_60']: 
                total_score += 10
                trend_desc = "多頭排列"
            if latest['MA_5'] > df_price.iloc[-2]['MA_5']: total_score += 5
            if latest['Volume'] > df_price.iloc[-2]['Vol_MA5'] * 1.1: total_score += 10
    except: trend_desc = "報價延遲"

    # 2. 營收基本面
    try:
        res_rev = requests.get(FINMIND_URL, params={"dataset": "TaiwanStockMonthRevenue", "data_id": stock_id, "start_date": "2024-01-01"}, timeout=5)
        df_rev = pd.DataFrame(res_rev.json()['data'])
        if not df_rev.empty:
            df_rev['revenue'] = df_rev['revenue'].astype(float)
            df_rev['yoy'] = df_rev['revenue'].pct_change(12) * 100
            latest_yoy = float(df_rev.iloc[-1]['yoy'])
            latest_yoy_str = f"{latest_yoy:+.1f}%"
            if latest_yoy > 10: total_score += 10
    except: pass

    # 3. 財報獲利能力與【真名校正大腦】
    try:
        info = ticker.info
        # 如果是 FinMind 抓過來的或是自訂代碼，這裡會透過 Yahoo 財報資訊直接覆寫成真正的中文名稱（例如：2603 改成长榮）
        if default_name == stock_id or "個股" in default_name:
            actual_name = info.get('shortName', default_name)
            # 移除常見的英文尾綴，保持乾淨
            actual_name = actual_name.replace("CO.,LTD.", "").replace("LTD.", "").strip()
            
        gross_margin = info.get('grossMargins', 0) * 100 if info.get('grossMargins') else 0
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        if roe > 15 and gross_margin > 30: total_score += 15
