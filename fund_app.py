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

# --- 样式：养基宝专业风 ---
st.markdown("""
<style>
    .summary-card { background: #1c1e22; color: white; padding: 25px; border-radius: 12px; text-align: center; margin-bottom: 20px; border-top: 4px solid #b8860b; }
    .gold-row { display: flex; gap: 8px; margin-bottom: 10px; }
    .gold-box { flex: 1; background: #fffcf0; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #f0e6cc; }
    .gold-price { font-size: 1rem; font-weight: bold; color: #b8860b; }
    
    .fund-card { background: white; padding: 15px; margin-bottom: 12px; border-radius: 8px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .fund-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .fund-name { font-size: 1rem; font-weight: bold; color: #333; }
    
    .data-grid { display: flex; justify-content: space-between; text-align: center; }
    .data-item { flex: 1; }
    .label { color: #888; font-size: 0.75rem; margin-bottom: 3px; }
    .value { font-size: 0.95rem; font-weight: 600; }
    
    .up { color: #e03131 !important; }
    .down { color: #2f9e44 !important; }
    .time-tag { font-size: 0.7rem; color: #999; text-align: right; }
</style>
""", unsafe_allow_html=True)

# --- 1. 核心行情抓取 ---
def fetch_sina_fund(code):
    try:
        ts = int(time.time() * 1000)
        url = f"http://hq.sinajs.cn/list=f_{code}?_={ts}"
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as res:
            data = re.search(r'"([^"]+)"', res.read().decode('gbk')).group(1).split(',')
            curr, last = float(data[1]), float(data[3])
            now = datetime.now(TZ)
            is_gz = (9 <= now.hour < 15) and now.weekday() < 5
            return {
                "name": data[0], "curr": curr, "last": last,
                "rate": ((curr - last) / last) * 100,
                "date": now.strftime("%m-%d %H:%M") if is_gz else data[4],
                "mode": "今日估值" if is_gz else "今日净值"
            }
    except: return None

def fetch_gold_sina():
    d = {"au": 0.0, "xau": 0.0, "cny": 0.0}
    try:
        url = "http://hq.sinajs.cn/list=gds_AU9999,hf_XAU,fx_susdcnh"
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as res:
            raw = res.read().decode('gbk')
            m1 = re.search(r'gds_AU9999="([\d\.]+)', raw)
            m2 = re.search(r'hf_XAU="([\d\.]+)', raw)
            m3 = re.search(r'fx_susdcnh="[^,]+,([\d\.]+)', raw)
            if m1: d["au"] = float(m1.group(1))
            if m2: d["xau"] = float(m2.group(1))
            if m3: d["cny"] = (d["xau"] * float(m3.group(1))) / 31.1035
    except: pass
    return d

# --- 2. 持仓与侧边栏配置 ---
def load_json(p, d):
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    return d

cfg = load_json(USER_CONFIG_FILE, {"users": ["Default"], "current": "Default"})

with st.sidebar:
    st.header("👤 账户管理")
    cur_u = st.selectbox("当前登录", cfg["users"], index=cfg["users"].index(cfg["current"]))
    if cur_u != cfg["current"]:
        cfg["current"] = cur_u
        with open(USER_CONFIG_FILE, 'w') as f: json.dump(cfg, f)
        st.rerun()
    
    with st.expander("➕ 新增账号"):
        new_u = st.text_input("用户名")
        if st.button("立即创建"):
            if new_u and new_u not in cfg["users"]:
                cfg["users"].append(new_u); cfg["current"] = new_u
                with open(USER_CONFIG_FILE, 'w') as f: json.dump(cfg, f); st.rerun()
    st.divider()
    st.caption("🥛 睡前一小时记得喝杯热牛奶")

db_path = f"db_{cur_u}.json"
db = load_json(db_path, {"holdings": []})

# --- 3. 页面渲染 ---
refresh_time = datetime.now(TZ).strftime("%H:%M:%S")
c1, c2 = st.columns([4, 1])
c1.subheader(f"📊 {cur_u} 的资产看板")
if c2.button("🔄 刷新数据", type="primary", use_container_width=True): st.rerun()

# 黄金看板
g = fetch_gold_sina()
st.markdown(f"""
<div class="gold-row">
    <div class="gold-box">上海金<br><span class="gold-price">¥{g['au']:.2f}</span></div>
    <div class="gold-box">国际金<br><span class="gold-price">${g['xau']:.2f}</span></div>
    <div class="gold-box">折算价<br><span class="gold-price">¥{g['cny']:.2f}</span></div>
</div>
<div class="time-tag">最后同步: {refresh_time}</div>
""", unsafe_allow_html=True)

# 数据计算
total_m, total_d = 0.0, 0.0
res_list = []
if db["holdings"]:
    for h in db["holdings"]:
        f = fetch_sina_fund(h['code'])
        if f:
            sh, ct = float(h['shares']), float(h.get('cost', 0))
            day_p = sh * (f['curr'] - f['last'])
            total_m += (sh * f['curr']); total_d += day_p
            res_list.append({**f, "day_p": day_p, "shares": sh, "cost": ct})

    # 总揽卡片
    d_color = "up" if total_d >= 0 else "down"
    st.markdown(f"""
    <div class="summary-card">
        <div style="font-size:0.85rem; opacity:0.8;">总资产市值 (元)</div>
        <div style="font-size:1.8rem; font-weight:bold; margin:8px 0;">{total_m:,.2f}</div>
        <div style="font-size:1.1rem;">当日收益：<span class="{d_color}">{total_d:+.2f}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # 基金列表
    for f in res_list:
        c = "up" if f['rate'] >= 0 else "down"
        st.markdown(f"""
        <div class="fund-card">
            <div class="fund-header">
                <div class="fund-name">{f['name']}</div>
                <div style="font-size:0.75rem; color:#999;">{f['date']}</div>
            </div>
            <div class="data-grid">
                <div class="data-item">
                    <div class="label">当日涨幅</div>
                    <div class="value {c}">{f['rate']:+.2f}%</div>
                </div>
                <div class="data-item">
                    <div class="label">当日收益</div>
                    <div class="value {c}">{f['day_p']:+.2f}</div>
                </div>
                <div class="data-item">
                    <div class="label">{f['mode']}</div>
                    <div class="value" style="color:#333;">{f['curr']:.4f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- 4. 管理面板 ---
st.divider()
with st.expander("⚙️ 持仓管理（新增/删除/成本设定）", expanded=False):
    col_add, col_del = st.columns(2)
    with col_add:
        st.markdown("##### ➕ 新增/修改")
        with st.form("add_form", clear_on_submit=True):
            fc = st.text_input("基金代码")
            fs = st.number_input("持有份额", value=None)
            fco = st.number_input("单位成本", value=None)
            if st.form_submit_button("保存", type="primary", use_container_width=True):
                if fc and fs:
                    db["holdings"] = [x for x in db["holdings"] if x["code"] != fc]
                    db["holdings"].append({"code": fc, "shares": fs, "cost": fco if fco else 0.0})
                    with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
                    st.rerun()
    with col_del:
        st.markdown("##### 🗑️ 删除持仓")
        codes = [h['code'] for h in db["holdings"]]
        target = st.selectbox("选择要移除的代码", ["请选择"] + codes)
        if st.button("确认删除", use_container_width=True) and target != "请选择":
            db["holdings"] = [x for x in db["holdings"] if x["code"] != target]
            with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
            st.rerun()
