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
    st.sidebar.info("📊 系統正透過 TWSE 每日收盤行情，依據最新交易日「實際成交股數」由高到低排序，自動篩選出前 50 檔正股。")
    
    @st.cache_data(ttl=1800)  # 緩存 30 分鐘
    def fetch_real_twse_top_50():
        try:
            # 取得最新一個交易日的日期 (如果是週末，自動往前推到週五)
            target_date = datetime.datetime.now()
            # 偽裝成真實瀏覽器的標頭 (核心防禦：防止 503 或 Expecting value 錯誤)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            # 嘗試最多往前推 5 天找尋有開盤的交易日數據
            for _ in range(5):
                date_str = target_date.strftime("%Y%m%d")
                url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALL"
                res = requests.get(url, headers=headers, timeout=10)
                
                # 確保收到的是正常的 JSON 格式
                if res.status_code == 200 and res.text.strip().startswith("{"):
                    data = res.json()
                    if 'data9' in data:  # data9 是全市場股票的收盤行情
                        raw_data = data['data9']
                        # 欄位說明：0:證券代號, 1:證券名稱, 2:成交股數, ...
                        df_all = pd.DataFrame(raw_data)
                        
                        # 清理並過濾正股：代號必須是 4 位數純數字
                        df_all[0] = df_all[0].str.strip()
                        df_all[1] = df_all[1].str.strip()
                        df_all = df_all[df_all[0].str.len() == 4]
                        df_all = df_all[df_all[0].str.isdigit()]
                        
                        # 將成交股數欄位(索引2)的逗號拿掉，轉為純數字以利排序
                        df_all[2] = df_all[2].str.replace(',', '')
                        df_all[2] = pd.to_numeric(df_all[2], errors='coerce')
                        
                        # 排序並取出前 50 名
                        df_top50 = df_all.sort_values(by=2, ascending=False).head(50)
                        
                        # 打包成字典
                        return dict(zip(df_top50[0], df_top50[1]))
                
                # 如果該日期沒開盤或抓取失敗，往前推一天
                target_date -= datetime.timedelta(days=1)
                
            raise Exception("無法取得近期的證交所開盤數據")
            
        except Exception as e:
            st.sidebar.error(f"❌ 證交所 API 解析異常，已啟用核心權值股替代方案。原因: {e}")
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
# 核心十一因子打分大腦
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

    # 3. 財報獲利能力與真名校正
    try:
        info = ticker.info
        if "個股" in default_name:
            actual_name = info.get('shortName', default_name)
        gross_margin = info.get('grossMargins', 0) * 100 if info.get('grossMargins') else 0
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        if roe > 15 and gross_margin > 30: total_score += 15
    except: pass

    # 4. 法人籌碼
    try:
        res_chips = requests.get(FINMIND_URL, params={"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": stock_id, "start_date": two_weeks_ago}, timeout=5)
        df_chips = pd.DataFrame(res_chips.json()['data'])
        if not df_chips.empty:
            df_chips['net'] = df_chips['buy'] - df_chips['sell']
            df_latest_chips = df_chips[df_chips['date'] == df_chips['date'].max()]
            f_net = df_latest_chips[df_latest_chips['name'].str.contains('Foreign|外資', case=False)]['net'].sum()
            t_net = df_latest_chips[df_latest_chips['name'].str.contains('Trust|投信', case=False)]['net'].sum()
            if f_net > 0 and t_net > 0: total_score += 12
            elif f_net > 0 or t_net > 0: total_score += 6
    except: pass

    # 5. 大戶持股
    try:
        res_hold = requests.get(FINMIND_URL, params={"dataset": "TaiwanStockShareholdingSelecIndices", "data_id": stock_id, "start_date": two_months_ago}, timeout=5)
        df_hold = pd.DataFrame(res_hold.json()['data'])
        if not df_hold.empty:
            df_400 = df_hold[df_hold['holding_shares_level'].str.contains('400', na=False)]
            if len(df_400) >= 2 and df_400.iloc[-1]['percent'] > df_400.iloc[-2]['percent']: total_score += 8
    except: pass

    # 總經加分
    if fx_bullish: total_score += 8
    if macro_growth: total_score += 7
    if us_bullish: total_score += 15

    return {"代號": stock_id, "股名": actual_name, "綜合總分": total_score, "最新股價": close_price_str, "營收YoY": latest_yoy_str, "技術型態": trend_desc}

# ==========================================
# 主網頁呈現
# ==========================================
st.title("🏆 今日台股量化多因子篩選器 · 策略爭霸榜")

# 展開查看當前抓到的50大名單
with st.expander("🔍 點擊查看當前證交所量能前 50 大股票池名單"):
    st.write(", ".join([f"{k} {v}" for k, v in stock_pool.items()]))

st.write(f"📊 當前選股池目標數量： **{len(stock_pool)}** 檔股票")

if len(stock_pool) > 20:
    st.warning(f"⚠️ 正在對大量熱門標的（共 {len(stock_pool)} 檔）進行深度因子計算。因配合 API 速限，約需 15~25 秒，請稍候。")

if st.button("🚀 啟動全自動量化因子雷達掃描", type="primary"):
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, (s_id, s_name) in enumerate(stock_pool.items()):
        status_text.text(f"⏳ 正在深度診斷：{s_id} {s_name} ...")
        stock_data = calculate_stock_score(s_id, s_name)
        results.append(stock_data)
        progress_bar.progress((idx + 1) / len(stock_pool))
        time.sleep(0.1)
        
    status_text.text("✅ 全市場熱門股因子掃描完成！")
    
    df_leaderboard = pd.DataFrame(results).sort_values(by="綜合總分", ascending=False).reset_index(drop=True)
    
    st.balloons()
    st.success(f"👑 本次成交量修羅場冠軍：【 {df_leaderboard.iloc[0]['股名']} 】（獲得 {df_leaderboard.iloc[0]['綜合總分']} 分）")
    st.dataframe(df_leaderboard, use_container_width=True)
