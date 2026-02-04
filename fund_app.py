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

# --- 样式逻辑 ---
st.markdown("""
<style>
    .summary-card { background: #1c1e22; color: white; padding: 25px; border-radius: 12px; text-align: center; margin-bottom: 20px; border-top: 4px solid #b8860b; }
    .gold-row { display: flex; gap: 8px; margin-bottom: 10px; }
    .gold-box { flex: 1; background: #fffcf0; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #f0e6cc; }
    .gold-price { font-size: 1rem; font-weight: bold; color: #b8860b; }
    .fund-card { background: white; padding: 15px; margin-bottom: 12px; border-radius: 8px; border: 1px solid #eee; }
    .data-grid { display: flex; justify-content: space-between; text-align: center; }
    .label { color: #888; font-size: 0.75rem; margin-bottom: 3px; }
    .value { font-size: 0.95rem; font-weight: 600; }
    .up { color: #e03131 !important; }
    .down { color: #2f9e44 !important; }
</style>
""", unsafe_allow_html=True)

# --- 1. 行情引擎（增强防屏蔽版） ---
def fetch_sina_fund(code):
    # 自动处理代码格式：如果没带 f_ 则补上
    clean_code = code if code.startswith('f_') else f'f_{code}'
    try:
        ts = int(time.time() * 1000)
        url = f"http://hq.sinajs.cn/list={clean_code}?_={ts}"
        headers = {
            'Referer': 'http://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as res:
            content = res.read().decode('gbk')
            match = re.search(r'"([^"]+)"', content)
            if not match or not match.group(1): return None
            data = match.group(1).split(',')
            
            curr, last = float(data[1]), float(data[3])
            now = datetime.now(TZ)
            # 交易时段判断：周一至周五 9:15-15:00
            is_gz = (9 <= now.hour < 15) and now.weekday() < 5
            
            return {
                "name": data[0], "curr": curr, "last": last,
                "rate": ((curr - last) / last) * 100,
                "date": now.strftime("%m-%d %H:%M") if is_gz else data[4],
                "mode": "今日估值" if is_gz else "今日净值"
            }
    except Exception as e:
        return None

def fetch_gold_all():
    res = {"au": 0.0, "xau": 0.0, "cny": 0.0}
    try:
        url = "http://hq.sinajs.cn/list=gds_AU9999,hf_XAU,fx_susdcnh"
        headers = {'Referer': 'http://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as r:
            raw = r.read().decode('gbk')
            m_au = re.search(r'gds_AU9999="([\d\.]+)', raw)
            m_xau = re.search(r'hf_XAU="([\d\.]+)', raw)
            m_fx = re.search(r'fx_susdcnh="[^,]+,([\d\.]+)', raw)
            if m_au: res["au"] = float(m_au.group(1))
            if m_xau: res["xau"] = float(m_xau.group(1))
            if m_fx: res["cny"] = (res["xau"] * float(m_fx.group(1))) / 31.1035
    except: pass
    return res

# --- 2. 配置与侧边栏 ---
def load_json(p, d):
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    return d

cfg = load_json(USER_CONFIG_FILE, {"users": ["Default"], "current": "Default"})

with st.sidebar:
    st.header("👤 用户系统")
    cur_u = st.selectbox("当前登录账户", cfg["users"], index=cfg["users"].index(cfg["current"]))
    if cur_u != cfg["current"]:
        cfg["current"] = cur_u
        with open(USER_CONFIG_FILE, 'w') as f: json.dump(cfg, f)
        st.rerun()
    
    with st.expander("➕ 新增用户"):
        new_u = st.text_input("输入用户名")
        if st.button("创建新账户"):
            if new_u and new_u not in cfg["users"]:
                cfg["users"].append(new_u); cfg["current"] = new_u
                with open(USER_CONFIG_FILE, 'w') as f: json.dump(cfg, f); st.rerun()
    st.divider()
    st.caption("🥛 睡前一小时记得喝杯热牛奶")

db_path = f"db_{cur_u}.json"
db = load_json(db_path, {"holdings": []})

# --- 3. 渲染主界面 ---
now_time = datetime.now(TZ).strftime("%H:%M:%S")
c1, c2 = st.columns([4, 1])
c1.subheader(f"📊 {cur_u} 的资产看板")
if c2.button("🔄 刷新数据", type="primary", use_container_width=True): st.rerun()

# 黄金看板
g = fetch_gold_all()
st.markdown(f"""
<div class="gold-row">
    <div class="gold-box">上海金<br><span class="gold-price">¥{g['au']:.2f}</span></div>
    <div class="gold-box">美黄金<br><span class="gold-price">${g['xau']:.2f}</span></div>
    <div class="gold-box">折算价<br><span class="gold-price">¥{g['cny']:.2f}</span></div>
</div>
<div style="text-align:right; font-size:0.7rem; color:#999; margin-bottom:10px;">数据更新时间: {now_time}</div>
""", unsafe_allow_html=True)

# 持仓逻辑
total_m, total_d = 0.0, 0.0
res_list = []
if db["holdings"]:
    for h in db["holdings"]:
        f = fetch_sina_fund(h['code'])
        if f:
            sh, cost = float(h['shares']), float(h.get('cost', 0))
            day_p = sh * (f['curr'] - f['last'])
            total_m += (sh * f['curr']); total_d += day_p
            res_list.append({**f, "day_p": day_p})
        else:
            st.warning(f"无法获取代码 {h['code']} 的数据，请检查代码是否正确或稍后刷新。")

    if res_list:
        p_color = "up" if total_d >= 0 else "down"
        st.markdown(f"""
        <div class="summary-card">
            <div style="font-size:0.85rem; opacity:0.8;">账户总资产 (元)</div>
            <div style="font-size:1.8rem; font-weight:bold; margin:8px 0;">{total_m:,.2f}</div>
            <div style="font-size:1.1rem;">当日收益：<span class="{p_color}">{total_d:+.2f}</span></div>
        </div>
        """, unsafe_allow_html=True)

        for f in res_list:
            c = "up" if f['rate'] >= 0 else "down"
            st.markdown(f"""
            <div class="fund-card">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <b style="color:#333;">{f['name']}</b>
                    <span style="font-size:0.75rem; color:#999;">{f['date']}</span>
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
with st.expander("⚙️ 持仓管理（增/删/改成本）", expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        with st.form("add_form", clear_on_submit=True):
            fc = st.text_input("基金代码 (如: 000001)")
            fs = st.number_input("持有份额", value=None)
            fco = st.number_input("单位成本 (元)", value=None)
            if st.form_submit_button("确认保存", use_container_width=True):
                if fc and fs:
                    db["holdings"] = [x for x in db["holdings"] if x["code"] != fc]
                    db["holdings"].append({"code": fc, "shares": fs, "cost": fco if fco else 0.0})
                    with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
                    st.rerun()
    with col_b:
        h_codes = [x['code'] for x in db["holdings"]]
        target = st.selectbox("选择要删除的代码", ["请选择"] + h_codes)
        if st.button("立即移除持仓", use_container_width=True) and target != "请选择":
            db["holdings"] = [x for x in db["holdings"] if x["code"] != target]
            with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
            st.rerun()
