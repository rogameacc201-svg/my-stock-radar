import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="台股量化選股雷達", layout="wide")

# ==========================================
# 核心資料處理：抓取特定日期的證交所 CSV
# ==========================================
def fetch_top_50_data():
    # 使用 2026-06-05 作為最近交易日
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date=20260605&type=ALL"
    try:
        # 讀取 CSV，確保欄位對齊
        df = pd.read_csv(url, header=1, thousands=',', encoding='cp950')
        # 過濾證券代號為 4 位數的股票 (去掉權證與其他)
        df = df[df['證券代號'].astype(str).str.len() == 4]
        # 依照成交股數排序，取前 50
        df = df.sort_values(by='成交股數', ascending=False).head(50)
        return dict(zip(df['證券代號'].astype(str), df['證券名稱']))
    except Exception as e:
        st.error(f"無法取得證交所資料: {e}")
        return {}

# ==========================================
# 側邊欄：功能選擇
# ==========================================
st.sidebar.header("⚙️ 設定面板")
mode = st.sidebar.radio("選擇模式：", ("🔥 自動抓取前 50 大熱門股", "✍️ 自訂輸入"))

stock_pool = {}

if mode == "🔥 自動抓取前 50 大熱門股":
    if st.sidebar.button("載入熱門股"):
        stock_pool = fetch_top_50_data()
else:
    user_input = st.sidebar.text_input("輸入股票代號 (逗號分隔):", "2330, 2317, 2454")
    if user_input:
        for s_id in user_input.split(','):
            clean_id = s_id.strip()
            if clean_id.isdigit():
                stock_pool[clean_id] = f"個股 {clean_id}"

# ==========================================
# 呈現結果
# ==========================================
st.title("🏆 台股選股雷達")

if stock_pool:
    st.write(f"目前分析標的數量：{len(stock_pool)}")
    # 在這裡顯示簡單的清單，讓你確認沒跑掉
    st.table(pd.DataFrame(list(stock_pool.items()), columns=["代號", "名稱"]))
    
    if st.button("開始執行深度分析"):
        st.info("分析功能已就緒，請檢查上述清單是否正確。")
else:
    st.write("請從左側側邊欄選擇模式並載入標的。")
