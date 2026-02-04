import streamlit as st
from datetime import datetime
import json
import os
import urllib.request
import ssl
import re
import pytz

# --- 1. 基础配置与安全 ---
TZ = pytz.timezone('Asia/Shanghai')
USER_CONFIG_FILE = "user_config_new.json"
ssl_ctx = ssl._create_unverified_context()

st.set_page_config(page_title="资产管理 Pro", layout="wide")

# --- 样式 (养基宝复刻) ---
st.markdown("""
<style>
    .summary-card { background: #1c1e22; color: white; padding: 25px; border-radius: 12px; text-align: center; margin-bottom: 20px; }
    .fund-card { background: white; padding: 15px; margin-bottom: 12px; border-radius: 8px; border: 1px solid #eee; }
    .data-grid { display: flex; justify-content: space-between; text-align: center; }
    .label { color: #888; font-size: 0.75rem; }
    .value { font-size: 1rem; font-weight: 600; }
    .up { color: #e03131 !important; }
    .down { color: #2f9e44 !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. 增强型抓取引擎 (双源备份) ---
def fetch_fund_data(code):
    code = re.sub(r'\D', '', code)
    if not code: return None
    
    # 策略 A: 天天基金接口 (云端兼容性更好)
    try:
        url = f"http://fundgz.1234567.com.cn/js/{code}.js?rt={int(datetime.now().timestamp())}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as res:
            content = res.read().decode('utf-8')
            # 解析 jsonpgz(...) 格式
            match = re.search(r'jsonpgz\((.*)\)', content)
            if match:
                data = json.loads(match.group(1))
                curr = float(data['gsz']) # 估值
                last = float(data['dwjz']) # 昨净
                now = datetime.now(TZ)
                return {
                    "name": data['name'], "curr": curr, "last": last,
                    "rate": float(data['gszzl']),
                    "date": data['gztime'], "mode": "今日估值"
                }
    except: pass

    # 策略 B: 新浪备用 (如果 A 失败)
    try:
        url = f"http://hq.sinajs.cn/list=f_{code}"
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as res:
            line = res.read().decode('gbk')
            parts = re.search(r'"([^"]+)"', line).group(1).split(',')
            curr, last = float(parts[1]), float(parts[3])
            if curr == 0: curr = last
            return {
                "name": parts[0], "curr": curr, "last": last,
                "rate": ((curr - last) / last) * 100,
                "date": parts[4], "mode": "当日净值"
            }
    except: return None

# --- 3. 持久化层 ---
def get_db_path(user):
    # 使用绝对路径确保云端写入成功
    return os.path.join(os.getcwd(), f"fund_db_{user}.json")

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

# --- 4. 侧边栏与账户 ---
cfg = load_json(USER_CONFIG_FILE, {"users": ["Default"], "current": "Default"})

with st.sidebar:
    st.header("👤 账户管理")
    cur_u = st.selectbox("切换用户", cfg["users"], index=cfg["users"].index(cfg["current"]))
    if cur_u != cfg["current"]:
        cfg["current"] = cur_u
        save_json(USER_CONFIG_FILE, cfg)
        st.rerun()
    
    new_u = st.text_input("新增账号名")
    if st.button("创建账户"):
        if new_u and new_u not in cfg["users"]:
            cfg["users"].append(new_u); cfg["current"] = new_u
            save_json(USER_CONFIG_FILE, cfg); st.rerun()
    st.divider()
    st.caption("🥛 睡前一小时喝杯热牛奶")

db = load_json(get_db_path(cur_u), {"holdings": []})

# --- 5. 主页面渲染 ---
st.subheader(f"📊 {cur_u} 的资产看板")

# 强制 Debug (如果数据为空)
if not db["holdings"]:
    st.warning("⚠️ 数据库中没有持仓。请在页面底部添加代码、份额和成本。")
else:
    total_m, total_d = 0.0, 0.0
    res_list = []
    
    with st.spinner('正在同步行情...'):
        for h in db["holdings"]:
            f = fetch_fund_data(h['code'])
            if f:
                sh = float(h['shares'])
                day_p = sh * (f['curr'] - f['last'])
                total_m += (sh * f['curr'])
                total_d += day_p
                res_list.append({**f, "day_p": day_p})

    if res_list:
        p_c = "up" if total_d >= 0 else "down"
        st.markdown(f"""
        <div class="summary-card">
            <div style="font-size:0.85rem; opacity:0.8;">账户总资产 (元)</div>
            <div style="font-size:1.8rem; font-weight:bold; margin:8px 0;">{total_m:,.2f}</div>
            <div style="font-size:1.1rem;">当日收益：<span class="{p_c}">{total_d:+.2f}</span></div>
        </div>
        """, unsafe_allow_html=True)

        for f in res_list:
            c = "up" if f['rate'] >= 0 else "down"
            st.markdown(f"""
            <div class="fund-card">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <b>{f['name']}</b><span style="font-size:0.75rem; color:#999;">{f['date']}</span>
                </div>
                <div class="data-grid">
                    <div class="data-item"><div class="label">当日涨幅</div><div class="value {c}">{f['rate']:+.2f}%</div></div>
                    <div class="data-item"><div class="label">当日收益</div><div class="value {c}">{f['day_p']:+.2f}</div></div>
                    <div class="data-item"><div class="label">{f['mode']}</div><div class="value" style="color:#333;">{f['curr']:.4f}</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.error("❌ 已有持仓代码，但无法从接口获取行情。请检查网络或代码是否正确。")

# --- 6. 持仓管理 ---
st.divider()
with st.expander("⚙️ 持仓管理 (在此添加数据)", expanded=not db["holdings"]):
    ca, cb = st.columns(2)
    with ca:
        with st.form("add_fund_form"):
            f_code = st.text_input("基金代码 (例如: 000001)")
            f_shares = st.number_input("持有份额", step=0.01)
            f_cost = st.number_input("单位成本", step=0.0001)
            if st.form_submit_button("确认保存并刷新"):
                if f_code and f_shares > 0:
                    # 更新逻辑
                    new_holdings = [x for x in db["holdings"] if x["code"] != f_code]
                    new_holdings.append({"code": f_code, "shares": f_shares, "cost": f_cost})
                    db["holdings"] = new_holdings
                    save_json(get_db_path(cur_u), db)
                    st.success(f"代码 {f_code} 已保存！页面即将刷新...")
                    time.sleep(1)
                    st.rerun()
    with cb:
        if db["holdings"]:
            target = st.selectbox("移除持仓", [x['code'] for x in db["holdings"]])
            if st.button("确认删除"):
                db["holdings"] = [x for x in db["holdings"] if x["code"] != target]
                save_json(get_db_path(cur_u), db)
                st.rerun()
