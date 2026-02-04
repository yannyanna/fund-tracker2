import streamlit as st
from datetime import datetime
import json
import os
import urllib.request
import ssl
import re
import pytz
import time

# --- 基础配置 ---
TZ = pytz.timezone('Asia/Shanghai')
USER_CONFIG_FILE = "user_config.json"
ssl_ctx = ssl._create_unverified_context()

st.set_page_config(page_title="资产管理 Pro", layout="wide")

# --- 样式：极致还原养基宝色彩 ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .summary-card { background: #1c1e22; color: white; padding: 25px; border-radius: 12px; text-align: center; margin-bottom: 20px; }
    .total-val { font-size: 1.8rem; font-weight: bold; margin: 10px 0; }
    .daily-profit { font-size: 1.1rem; }
    
    .fund-card { background: white; padding: 15px; margin-bottom: 12px; border-radius: 8px; border: 1px solid #eee; }
    .fund-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .fund-name { font-size: 1.05rem; font-weight: bold; color: #333; }
    .fund-date { font-size: 0.75rem; color: #999; }
    
    .data-grid { display: flex; justify-content: space-between; text-align: center; }
    .data-item { flex: 1; }
    .label { color: #888; font-size: 0.8rem; margin-bottom: 4px; }
    .value { font-size: 1rem; font-weight: 600; }
    
    .up { color: #e03131 !important; } /* 养基宝风格红 */
    .down { color: #2f9e44 !important; } /* 养基宝风格绿 */
    .time-tag { font-size: 0.75rem; color: #999; text-align: right; margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

# --- 1. 智能行情引擎 ---
def fetch_sina_market(code):
    try:
        ts = int(time.time() * 1000)
        url = f"http://hq.sinajs.cn/list=f_{code}?_={ts}"
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as res:
            content = res.read().decode('gbk')
            raw = re.search(r'"([^"]+)"', content).group(1).split(',')
            
            # 字段定义：0:名称, 1:当前价(估/净), 3:昨日净值, 4:日期
            curr_val = float(raw[1])
            last_jz = float(raw[3])
            rate = ((curr_val - last_jz) / last_jz) * 100
            
            # 自动判断当前模式
            now = datetime.now(TZ)
            is_gz = (9 <= now.hour < 15) and now.weekday() < 5
            mode_text = "当日估值" if is_gz else "当日净值"
            
            return {
                "name": raw[0],
                "curr": curr_val,
                "last": last_jz,
                "rate": rate,
                "date": now.strftime("%m-%d") if is_gz else raw[4][-5:], # 格式化为 MM-DD
                "mode": mode_text
            }
    except: return None

def fetch_gold():
    try:
        url = "http://hq.sinajs.cn/list=gds_AU9999,hf_XAU,fx_susdcnh"
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as res:
            raw = res.read().decode('gbk')
            m1 = re.search(r'gds_AU9999="([\d\.]+)', raw)
            return float(m1.group(1)) if m1 else 0.0
    except: return 0.0

# --- 2. 数据管理 ---
def load_json(p, d):
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    return d

cfg = load_json(USER_CONFIG_FILE, {"users": ["Default"], "current": "Default"})

with st.sidebar:
    st.header("👤 账户切换")
    cur_u = st.selectbox("当前账户", cfg["users"], index=cfg["users"].index(cfg["current"]))
    if cur_u != cfg["current"]:
        cfg["current"] = cur_u
        with open(USER_CONFIG_FILE, 'w') as f: json.dump(cfg, f)
        st.rerun()
    st.divider()
    st.caption("🥛 睡前一小时记得喝杯热牛奶")

db_path = f"db_{cur_u}.json"
db = load_json(db_path, {"holdings": []})

# --- 3. 页面渲染 ---
now_ts = datetime.now(TZ).strftime("%H:%M:%S")

# 顶部标题与刷新
col_t, col_r = st.columns([4, 1])
col_t.subheader(f"📊 {cur_u} 的持仓")
if col_r.button("🔄 刷新", use_container_width=True): st.rerun()

# 黄金快速看盘
au_price = fetch_gold()
st.markdown(f"""<div style='text-align:right; color:#b8860b; font-weight:bold; margin-bottom:10px;'>上海金实时: ¥{au_price:.2f} <span style='color:#999; font-weight:normal; font-size:0.7rem;'>({now_ts})</span></div>""", unsafe_allow_html=True)

# 计算核心数据
total_assets = 0.0
total_daily_profit = 0.0
fund_results = []

if db["holdings"]:
    for h in db["holdings"]:
        m = fetch_sina_market(h['code'])
        if m:
            shares = float(h['shares'])
            daily_profit = (m['curr'] - m['last']) * shares
            total_assets += (m['curr'] * shares)
            total_daily_profit += daily_profit
            fund_results.append({**m, "daily_p": daily_profit, "shares": shares})

    # 1. 顶部汇总卡片
    p_color = "up" if total_daily_profit >= 0 else "down"
    st.markdown(f"""
    <div class="summary-card">
        <div style="font-size:0.9rem; opacity:0.8;">总资产 (元)</div>
        <div class="total-val">{total_assets:,.2f}</div>
        <div class="daily-profit">当日收益：<span class="{p_color}">{total_daily_profit:+.2f}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # 2. 持仓列表（对标养基宝布局）
    for f in fund_results:
        c = "up" if f['rate'] >= 0 else "down"
        st.markdown(f"""
        <div class="fund-card">
            <div class="fund-header">
                <div class="fund-name">{f['name']}</div>
                <div class="fund-date">{f['date']} 更新</div>
            </div>
            <div class="data-grid">
                <div class="data-item">
                    <div class="label">当日涨幅</div>
                    <div class="value {c}">{f['rate']:+.2f}%</div>
                </div>
                <div class="data-item">
                    <div class="label">当日收益</div>
                    <div class="value {c}">{f['daily_p']:+.2f}</div>
                </div>
                <div class="data-item">
                    <div class="label">{f['mode']}</div>
                    <div class="value" style="color:#333;">{f['curr']:.4f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- 4. 收缩管理面板 ---
st.divider()
with st.expander("⚙️ 管理我的持仓", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        with st.form("add_fund", clear_on_submit=True):
            f_c = st.text_input("代码")
            f_s = st.number_input("份额", value=None)
            if st.form_submit_button("保存持仓", use_container_width=True):
                if f_c and f_s:
                    db["holdings"] = [x for x in db["holdings"] if x["code"] != f_c]
                    db["holdings"].append({"code": f_c, "shares": f_s})
                    with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
                    st.rerun()
    with c2:
        codes = [h['code'] for h in db["holdings"]]
        target = st.selectbox("选择要删除的基金", ["请选择"] + codes)
        if st.button("彻底删除该持仓", use_container_width=True) and target != "请选择":
            db["holdings"] = [x for x in db["holdings"] if x["code"] != target]
            with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
            st.rerun()
