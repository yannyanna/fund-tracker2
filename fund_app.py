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
# 禁用 SSL 验证，防止云端证书报错
ssl_ctx = ssl._create_unverified_context()

st.set_page_config(page_title="资产管理 Pro", layout="wide")

# --- 养基宝风格样式 ---
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

# --- 1. 核心行情抓取（云端抗干扰版） ---
def fetch_sina_fund(code):
    # 自动清理代码，确保格式为 f_xxxxxx
    code = re.sub(r'\D', '', code)
    if not code: return None
    full_code = f"f_{code}"
    
    try:
        # 使用随机时间戳绕过缓存
        url = f"http://hq.sinajs.cn/list={full_code}?_={int(time.time())}"
        req = urllib.request.Request(url)
        req.add_header('Referer', 'http://finance.sina.com.cn')
        
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as res:
            line = res.read().decode('gbk')
            data_match = re.search(r'"([^"]+)"', line)
            if not data_match: return None
            parts = data_match.group(1).split(',')
            if len(parts) < 5: return None
            
            curr = float(parts[1])
            last = float(parts[3])
            # 如果当前价为0，说明还没开盘或接口数据未同步
            if curr == 0: curr = last 
            
            now = datetime.now(TZ)
            is_gz = (9 <= now.hour < 15) and now.weekday() < 5
            
            return {
                "name": parts[0], "curr": curr, "last": last,
                "rate": ((curr - last) / last) * 100 if last != 0 else 0,
                "date": now.strftime("%m-%d %H:%M") if is_gz else parts[4],
                "mode": "今日估值" if is_gz else "今日净值"
            }
    except Exception:
        return None

def fetch_gold_prices():
    res = {"au": 0.0, "xau": 0.0, "cny": 0.0}
    try:
        url = "http://hq.sinajs.cn/list=gds_AU9999,hf_XAU,fx_susdcnh"
        req = urllib.request.Request(url)
        req.add_header('Referer', 'http://finance.sina.com.cn')
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as r:
            text = r.read().decode('gbk')
            m_au = re.search(r'gds_AU9999="([\d\.]+)', text)
            m_xau = re.search(r'hf_XAU="([\d\.]+)', text)
            m_fx = re.search(r'fx_susdcnh="[^,]+,([\d\.]+)', text)
            if m_au: res["au"] = float(m_au.group(1))
            if m_xau: res["xau"] = float(m_xau.group(1))
            if m_fx: res["cny"] = (res["xau"] * float(m_fx.group(1))) / 31.1035
    except: pass
    return res

# --- 2. 配置与多用户系统 ---
def load_data(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: return default
    return default

cfg = load_data(USER_CONFIG_FILE, {"users": ["Default"], "current": "Default"})

with st.sidebar:
    st.header("👤 用户系统")
    cur_u = st.selectbox("切换账号", cfg["users"], index=cfg["users"].index(cfg["current"]))
    if cur_u != cfg["current"]:
        cfg["current"] = cur_u
        with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(cfg, f)
        st.rerun()
    
    with st.expander("➕ 新增账号"):
        new_name = st.text_input("账号名称")
        if st.button("确认创建"):
            if new_name and new_name not in cfg["users"]:
                cfg["users"].append(new_name); cfg["current"] = new_name
                with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(cfg, f)
                st.rerun()
    st.divider()
    st.caption("🥛 睡前一小时记得喝杯热牛奶")

db_path = f"db_{cur_u}.json"
db = load_data(db_path, {"holdings": []})

# --- 3. 渲染页面 ---
c1, c2 = st.columns([4, 1])
c1.subheader(f"📊 {cur_u} 的看板")
if c2.button("🔄 刷新", type="primary", use_container_width=True): st.rerun()

# 黄金模块
g = fetch_gold_prices()
st.markdown(f"""
<div class="gold-row">
    <div class="gold-box">上海金<br><span class="gold-price">¥{g['au']:.2f}</span></div>
    <div class="gold-box">美黄金<br><span class="gold-price">${g['xau']:.2f}</span></div>
    <div class="gold-box">折算价<br><span class="gold-price">¥{g['cny']:.2f}</span></div>
</div>
""", unsafe_allow_html=True)

# 基金逻辑
total_m, total_d = 0.0, 0.0
res_list = []
for h in db["holdings"]:
    f_data = fetch_sina_fund(h['code'])
    if f_data:
        shares = float(h['shares'])
        daily_p = shares * (f_data['curr'] - f_data['last'])
        total_m += (shares * f_data['curr'])
        total_d += daily_p
        res_list.append({**f_data, "day_p": daily_p})

if res_list:
    p_col = "up" if total_d >= 0 else "down"
    st.markdown(f"""
    <div class="summary-card">
        <div style="font-size:0.85rem; opacity:0.8;">账户总资产 (元)</div>
        <div style="font-size:1.8rem; font-weight:bold; margin:8px 0;">{total_m:,.2f}</div>
        <div style="font-size:1.1rem;">当日收益：<span class="{p_col}">{total_d:+.2f}</span></div>
    </div>
    """, unsafe_allow_html=True)

    for f in res_list:
        c = "up" if f['rate'] >= 0 else "down"
        st.markdown(f"""
        <div class="fund-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                <b>{f['name']}</b>
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
else:
    st.info("暂无持仓数据，请在下方管理面板添加。")

# --- 4. 持仓管理面板 ---
st.divider()
with st.expander("⚙️ 持仓管理面板", expanded=False):
    ca, cb = st.columns(2)
    with ca:
        with st.form("add_fund", clear_on_submit=True):
            f_code = st.text_input("代码 (例如: 000001)")
            f_shares = st.number_input("份额", value=None)
            f_cost = st.number_input("成本", value=None)
            if st.form_submit_button("保存持仓", use_container_width=True):
                if f_code and f_shares:
                    db["holdings"] = [x for x in db["holdings"] if x["code"] != f_code]
                    db["holdings"].append({"code": f_code, "shares": f_shares, "cost": f_cost or 0.0})
                    with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
                    st.rerun()
    with cb:
        h_list = [x['code'] for x in db["holdings"]]
        target = st.selectbox("删除持仓", ["请选择"] + h_list)
        if st.button("确认删除", use_container_width=True) and target != "请选择":
            db["holdings"] = [x for x in db["holdings"] if x["code"] != target]
            with open(db_path, 'w', encoding='utf-8') as f: json.dump(db, f)
            st.rerun()
