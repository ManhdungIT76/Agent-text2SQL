import sys
import time
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

st.set_page_config(
    page_title="Dashboard Quản Lý - DVD Rental Enterprise",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}

.kpi-card{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);border:1px solid #334155;border-radius:16px;padding:20px 24px;position:relative;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.3);margin-bottom:6px;}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:16px 16px 0 0;}
.kpi-card.blue::before{background:linear-gradient(90deg,#38bdf8,#818cf8);}
.kpi-card.green::before{background:linear-gradient(90deg,#34d399,#10b981);}
.kpi-card.orange::before{background:linear-gradient(90deg,#fb923c,#f97316);}
.kpi-card.purple::before{background:linear-gradient(90deg,#c084fc,#a855f7);}
.kpi-card.red::before{background:linear-gradient(90deg,#f87171,#ef4444);}
.kpi-icon{font-size:1.7rem;margin-bottom:5px;}
.kpi-label{color:#94a3b8;font-size:.73rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;}
.kpi-value{color:#f1f5f9;font-size:1.65rem;font-weight:700;margin:3px 0;}
.kpi-up{color:#34d399;font-size:.8rem;font-weight:600;}
.kpi-down{color:#f87171;font-size:.8rem;font-weight:600;}
.kpi-note{color:#475569;font-size:.71rem;margin-top:4px;}

.alert-error{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.35);border-left:4px solid #ef4444;border-radius:10px;padding:12px 16px;margin:8px 0;}
.alert-warn{background:rgba(251,146,60,.1);border:1px solid rgba(251,146,60,.35);border-left:4px solid #fb923c;border-radius:10px;padding:12px 16px;margin:6px 0;}
.alert-ok{background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.25);border-radius:10px;padding:9px 16px;margin:8px 0;color:#34d399;font-size:.83rem;}

.dash-header{background:linear-gradient(135deg,#0f172a,#1e293b);border:1px solid #334155;border-radius:16px;padding:20px 28px;margin-bottom:18px;box-shadow:0 8px 24px rgba(0,0,0,.3);}
.dash-title{background:linear-gradient(90deg,#38bdf8 0%,#818cf8 50%,#c084fc 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1.8rem;font-weight:800;margin:0;}
.dash-sub{color:#64748b;font-size:.87rem;margin-top:3px;}
.badge{display:inline-block;padding:3px 11px;border-radius:20px;font-size:.73rem;font-weight:600;margin-top:7px;margin-right:5px;}
.badge-b{background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);color:#38bdf8;}
.badge-p{background:rgba(129,140,248,.12);border:1px solid rgba(129,140,248,.3);color:#818cf8;}
.badge-g{background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.3);color:#34d399;}

.badge-sel { background-color: #0284c7; color: white; padding: 5px 12px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; margin-right: 8px; margin-bottom: 6px; display: inline-block; }
.badge-conn { background-color: #d97706; color: white; padding: 5px 12px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; margin-right: 8px; margin-bottom: 6px; display: inline-block; }

.sec-hdr{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:12px;padding:12px 18px;margin:22px 0 12px 0;}

.sec-title{background:linear-gradient(90deg,#38bdf8,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1rem;font-weight:700;}

.chat-hdr{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-top:3px solid #818cf8;border-radius:12px;padding:14px 20px;margin:26px 0 12px 0;}
</style>
""", unsafe_allow_html=True)

# ── BACKEND IMPORTS ───────────────────────────────────────────────────────────
from app.config import config
from app.database.connection import get_db_connection
from app.database.executor import execute_sql
from app.agent.graph import text2sql_agent_graph, get_langfuse_handler
from app.metadata.openmetadata_client import om_client
from app.langfuse_utils import flush_all, check_langfuse_connection

# ── SESSION STATE ─────────────────────────────────────────────────────────────
for k, v in [("mgr_msgs", []), ("mgr_qcount", 0), ("mgr_lat", None), ("mgr_period", "🏢 Theo Năm (12 Tháng)"), ("mgr_month", 4)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── PACK MODE: KPI QUERIES ────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_kpi(_uri: str, period: str = "🏢 Theo Năm (12 Tháng)", selected_month: int = 4, store_f: str = "Tất cả") -> dict:
    db = get_db_connection()
    d = {}
    try:
        ref = execute_sql(db, "SELECT MAX(payment_date)::date AS today, (MAX(payment_date)::date - INTERVAL '1 day')::date AS yesterday FROM payment;")
        today, yesterday = str(ref[0]["today"]), str(ref[0]["yesterday"])
        d["today"], d["yesterday"] = today, yesterday

        store_clause = ""
        if store_f == "Cơ sở 1":
            store_clause = " AND p.staff_id IN (SELECT staff_id FROM staff WHERE store_id = 1) "
        elif store_f == "Cơ sở 2":
            store_clause = " AND p.staff_id IN (SELECT staff_id FROM staff WHERE store_id = 2) "

        if period == "🗓️ Theo Tháng (Đủ Ngày)":
            start_date = f"2007-{selected_month:02d}-01"
            prev_m = selected_month - 1 if selected_month > 1 else 12
            prev_y = 2007 if selected_month > 1 else 2006
            prev_start_date = f"{prev_y}-{prev_m:02d}-01"

            rt = execute_sql(db, f"SELECT COALESCE(SUM(p.amount),0) AS rev, COUNT(*) AS txn FROM payment p WHERE DATE_TRUNC('month', p.payment_date) = '{start_date}' {store_clause};")
            ry = execute_sql(db, f"SELECT COALESCE(SUM(p.amount),0) AS rev, COUNT(*) AS txn FROM payment p WHERE DATE_TRUNC('month', p.payment_date) = '{prev_start_date}' {store_clause};")
            d["lbl_t"] = f"THÁNG {selected_month:02d}/2007"
            d["lbl_y"] = f"tháng {prev_m:02d}/{prev_y}"
            d["note_t"] = f"🗓️ Hiển thị đủ ngày trong Tháng {selected_month:02d}/2007"

            raw_days = execute_sql(db, f"""
                SELECT 
                    d.day::date AS date_val,
                    TO_CHAR(d.day, 'DD/MM') AS ngay,
                    COALESCE(SUM(p.amount), 0) AS rev,
                    COUNT(p.payment_id) AS txn
                FROM generate_series('{start_date}'::date, ('{start_date}'::date + INTERVAL '1 month' - INTERVAL '1 day')::date, INTERVAL '1 day') AS d(day)
                LEFT JOIN payment p ON p.payment_date::date = d.day::date {store_clause}
                GROUP BY d.day
                ORDER BY d.day;""") or []

            d["trend_title"] = f"🗓️ Doanh Thu Đủ {len(raw_days)} Ngày Trong Tháng {selected_month:02d}/2007"
            d["trend"] = raw_days

        else: # "🏢 Theo Năm (12 Tháng)"
            rt = execute_sql(db, f"SELECT COALESCE(SUM(p.amount),0) AS rev, COUNT(*) AS txn FROM payment p WHERE EXTRACT(YEAR FROM p.payment_date) = 2007 {store_clause};")
            ry = execute_sql(db, f"SELECT COALESCE(SUM(p.amount),0) AS rev, COUNT(*) AS txn FROM payment p WHERE EXTRACT(YEAR FROM p.payment_date) = 2006 {store_clause};")
            d["lbl_t"] = "NĂM 2007"
            d["lbl_y"] = "năm trước (2006)"
            d["note_t"] = "🏢 Tổng hợp 12 tháng năm 2007"
            d["trend_title"] = "🏢 Doanh Thu Đủ 12 Tháng Trong Năm 2007"

            raw_m = execute_sql(db, f"""
                SELECT 
                    m.month_num,
                    'Tháng ' || LPAD(m.month_num::text, 2, '0') AS ngay,
                    COALESCE(SUM(p.amount), 0) AS rev,
                    COUNT(p.payment_id) AS txn
                FROM generate_series(1, 12) AS m(month_num)
                LEFT JOIN payment p ON EXTRACT(MONTH FROM p.payment_date) = m.month_num 
                                    AND EXTRACT(YEAR FROM p.payment_date) = 2007 {store_clause}
                GROUP BY m.month_num
                ORDER BY m.month_num;""") or []
            d["trend"] = raw_m

        d["rev_t"] = float(rt[0]["rev"]) if rt else 0.0
        d["txn_t"] = int(rt[0]["txn"]) if rt else 0
        d["rev_y"] = float(ry[0]["rev"]) if ry else 0.0
        d["txn_y"] = int(ry[0]["txn"]) if ry else 0

        d["stores"] = execute_sql(db, "SELECT store,manager,total_sales FROM sales_by_store ORDER BY total_sales DESC;") or []
        d["cats"]   = execute_sql(db, f"""
            SELECT fc.name AS category, COALESCE(SUM(p.amount),0) AS total_sales
            FROM payment p
            JOIN rental r ON p.rental_id = r.rental_id
            JOIN inventory i ON r.inventory_id = i.inventory_id
            JOIN film_category fcat ON i.film_id = fcat.film_id
            JOIN category fc ON fcat.category_id = fc.category_id
            WHERE 1=1 {store_clause}
            GROUP BY fc.name ORDER BY total_sales DESC LIMIT 5;""") or []

        lk = execute_sql(db, "SELECT COUNT(*) AS c FROM customer WHERE active=0;")
        tc = execute_sql(db, "SELECT COUNT(*) AS c FROM customer;")
        d["locked"] = int(lk[0]["c"]) if lk else 0
        d["total"]  = int(tc[0]["c"]) if tc else 0

        d["films"] = execute_sql(db, f"""
            SELECT f.title, COALESCE(SUM(p.amount),0) AS rev
            FROM payment p
            JOIN rental r ON p.rental_id=r.rental_id
            JOIN inventory i ON r.inventory_id=i.inventory_id
            JOIN film f ON i.film_id=f.film_id
            WHERE p.payment_date::date='{today}' {store_clause}
            GROUP BY f.title ORDER BY rev DESC LIMIT 5;""") or []
    except Exception as e:
        d["error"] = str(e)
    return d


def pct_delta(a, b):
    if b == 0: return 0.0, "flat"
    v = (a - b) / b * 100
    return v, ("up" if v >= 0 else "down")


def detect_alerts(d):
    out = []
    pct, _ = pct_delta(d["rev_t"], d["rev_y"])
    if pct < -20:
        out.append({"l":"error","t":f"⚠️ Doanh thu giảm mạnh {pct:.1f}% so với {d.get('lbl_y','kỳ trước')}","b":f"Kỳ trước ${d['rev_y']:,.2f} → Kỳ này ${d['rev_t']:,.2f}. Kiểm tra ngay!"})
    elif pct < -10:
        out.append({"l":"warn","t":f"📉 Doanh thu giảm {pct:.1f}% so với {d.get('lbl_y','kỳ trước')}","b":f"Kỳ trước ${d['rev_y']:,.2f} → Kỳ này ${d['rev_t']:,.2f}."})
    if d["locked"] > 5:
        out.append({"l":"warn","t":f"🔒 {d['locked']} khách hàng đang bị khóa","b":"Xem xét hỗ trợ để tránh ảnh hưởng đến doanh thu."})
    return out


def build_suggestions(d, alerts):
    base = [
        "Top 5 diễn viên có doanh thu cao nhất hôm nay?",
        "Khách hàng thanh toán nhiều nhất trong 7 ngày qua?",
        "Phim nào chưa được thuê trong tuần này?",
        "Nhân viên nào xử lý nhiều giao dịch nhất hôm nay?",
    ]
    extra = []
    for a in alerts:
        if "giam" in a["t"] or "giảm" in a["t"]: extra.insert(0, "Phân tích doanh thu hôm nay theo từng chi nhánh?")
        if "khoa" in a["t"] or "khóa" in a["t"]: extra.insert(0, "Danh sách khách hàng bị khóa kèm email để liên hệ?")
    if d["stores"]: extra.append(f"Chi tiết nhân viên tại {d['stores'][0].get('store',' Woodridge')}?")
    return (extra + base)[:6]


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:8px 0 14px"><div style="font-size:2.4rem">🏢</div><div style="color:#f1f5f9;font-weight:700;font-size:1rem">Manager Portal</div><div style="color:#64748b;font-size:.75rem">DVD Rental Enterprise</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    mgr_name = st.text_input("👤 Nhân viên quản lý", value="Nguyễn Văn A")
    st.caption(f"🕐 {time.strftime('%d/%m/%Y %H:%M')}")
    st.markdown("---")
    st.markdown("**📅 Mốc xem dữ liệu**")
    
    period_options = ["🏢 Theo Năm (12 Tháng)", "🗓️ Theo Tháng (Đủ Ngày)"]
    current_p = st.session_state.get("mgr_period", "🏢 Theo Năm (12 Tháng)")
    p_idx = period_options.index(current_p) if current_p in period_options else 0
    
    period = st.radio("period_radio", period_options, index=p_idx, label_visibility="collapsed")
    st.session_state.mgr_period = period

    if period == "🗓️ Theo Tháng (Đủ Ngày)":
        cur_m = st.session_state.get("mgr_month", 4)
        selected_m = st.selectbox(
            "📅 Chọn tháng xem chi tiết:",
            options=list(range(1, 13)),
            index=cur_m - 1,
            format_func=lambda x: f"Tháng {x:02d}/2007" + (" 💰" if x in [2, 3, 4, 5] else "")
        )
        st.session_state.mgr_month = selected_m
    else:
        st.markdown("**🔍 Drill-down theo tháng**")
        drill_m = st.selectbox(
            "drill_m_select",
            options=[0] + list(range(1, 13)),
            index=0,
            format_func=lambda x: "🔻 Chọn tháng để xem chi tiết..." if x == 0 else f"Tháng {x:02d}/2007" + (" 💰" if x in [2, 3, 4, 5] else ""),
            label_visibility="collapsed"
        )
        if drill_m > 0:
            st.session_state.mgr_period = "🗓️ Theo Tháng (Đủ Ngày)"
            st.session_state.mgr_month = drill_m
            st.rerun()

    st.markdown("**🏪 Chi nhánh**")
    store_f = st.selectbox("store", ["Tất cả", "Cơ sở 1", "Cơ sở 2"], label_visibility="collapsed")
    st.markdown("---")
    st.markdown("**⚡ Trạng thái hệ thống**")
    st.success("🟢 PostgreSQL: Hoạt động")
    if om_client.check_connection(): st.success("🟢 OpenMetadata: Online")
    else: st.info("🟡 OpenMetadata: Local Cache")
    if check_langfuse_connection():
        st.success("🟢 Langfuse Cloud: Đã Kết Nối")
    else:
        if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
            st.info("🟡 Langfuse: Key đã cấu hình")
        else:
            st.warning("🔴 Langfuse: Chưa cấu hình")
    st.markdown("---")
    if st.button("🔄 Làm mới Dashboard", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.session_state.mgr_lat: st.caption(f"⏱️ Thời gian phản hồi: {st.session_state.mgr_lat:.0f}ms")
    st.caption(f"💬 Số câu hỏi đã truy vấn: {st.session_state.mgr_qcount}")

# ── PAGE HEADER ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-header">
  <div class="dash-title">🏢 Dashboard Quản Lý Doanh Nghiệp</div>
  <div class="dash-sub">Theo dõi hiệu suất kinh doanh theo thời gian thực &bull; Drill-down bằng AI Chat</div>
  <div>
    <span class="badge badge-b">📦 PACK MODE – KPI Tự Động</span>
    <span class="badge badge-p">💬 STREAM MODE – AI Chat</span>
    <span class="badge badge-g">👤 {mgr_name}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── LOAD KPI ──────────────────────────────────────────────────────────────────
st.markdown('<div class="sec-hdr"><span style="font-size:1.1rem">📊</span> <span class="sec-title">PACK MODE — KPI Tự Động (Cập nhật mỗi 5 phút)</span></div>', unsafe_allow_html=True)

with st.spinner("⚡ Đang tải dữ liệu KPI từ PostgreSQL..."):
    kpi = load_kpi(config.DB_URI, period=st.session_state.mgr_period, selected_month=st.session_state.mgr_month, store_f=store_f)

if "error" in kpi:
    st.error(f"❌ Lỗi CSDL: {kpi['error']}")
    st.stop()

pct_r, dir_r = pct_delta(kpi.get("rev_t", 0.0), kpi.get("rev_y", 0.0))
pct_x, dir_x = pct_delta(kpi.get("txn_t", 0), kpi.get("txn_y", 0))
ar = "▲" if dir_r == "up" else "▼"
ax = "▲" if dir_x == "up" else "▼"
ts = kpi.get("stores", [{}])[0] if kpi.get("stores") else {}
locked_cnt = kpi.get("locked", 0)
total_cnt = kpi.get("total", 0)
lp = locked_cnt / total_cnt * 100 if total_cnt else 0

c1, c2, c3, c4 = st.columns(4)
with c1:
    lbl_t = kpi.get("lbl_t", "NĂM 2007")
    lbl_y = kpi.get("lbl_y", "kỳ trước")
    note_t = kpi.get("note_t", f"📅 Mốc dữ liệu: {kpi.get('today','')}")
    st.markdown(f"""<div class="kpi-card blue">
      <div class="kpi-icon">💰</div><div class="kpi-label">DOANH THU ({lbl_t})</div>
      <div class="kpi-value">${kpi.get('rev_t',0.0):,.2f}</div>
      <div class="kpi-{dir_r}">{ar} {abs(pct_r):.1f}% so với {lbl_y} (${kpi.get('rev_y',0.0):,.2f})</div>
      <div class="kpi-note">{note_t}</div></div>""", unsafe_allow_html=True)

with c2:
    rev_t_val = kpi.get("rev_t", 0.0)
    txn_t_val = kpi.get("txn_t", 0)
    avg = rev_t_val / txn_t_val if txn_t_val else 0
    st.markdown(f"""<div class="kpi-card green">
      <div class="kpi-icon">🧾</div><div class="kpi-label">SỐ GIAO DỊCH ({lbl_t})</div>
      <div class="kpi-value">{txn_t_val:,}</div>
      <div class="kpi-{dir_x}">{ax} {abs(pct_x):.1f}% so với {lbl_y} ({kpi.get('txn_y',0):,} GD)</div>
      <div class="kpi-note">Trung bình: ${avg:.2f}/GD</div></div>""", unsafe_allow_html=True)

with c3:
    store_name = str(ts.get('store', 'N/A')).replace(',', ', ')
    store_sales = float(ts.get('total_sales', 0))
    st.markdown(f"""<div class="kpi-card orange">
      <div class="kpi-icon">🏆</div><div class="kpi-label">CHI NHÁNH DẪN ĐẦU</div>
      <div class="kpi-value">${store_sales:,.2f}</div>
      <div class="kpi-up">🏢 {store_name}</div>
      <div class="kpi-note">👔 Quản lý: {ts.get('manager','N/A')}</div></div>""", unsafe_allow_html=True)

with c4:
    cc = "red" if locked_cnt > 5 else "purple"
    st.markdown(f"""<div class="kpi-card {cc}">
      <div class="kpi-icon">👥</div><div class="kpi-label">KHÁCH HÀNG</div>
      <div class="kpi-value">{total_cnt:,}</div>
      <div class="kpi-down">🔒 {locked_cnt} bị khóa ({lp:.1f}%)</div>
      <div class="kpi-note">✅ {total_cnt - locked_cnt:,} đang hoạt động</div></div>""", unsafe_allow_html=True)

# ── ALERTS ────────────────────────────────────────────────────────────────────
alerts = detect_alerts(kpi)
if alerts:
    for a in alerts:
        cls = "alert-error" if a["l"] == "error" else "alert-warn"
        col = "#fca5a5" if a["l"] == "error" else "#fdba74"
        st.markdown(f'<div class="{cls}"><div style="color:{col};font-weight:700;font-size:.88rem">{a["t"]}</div><div style="color:#94a3b8;font-size:.8rem;margin-top:2px">{a["b"]}</div></div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="alert-ok">✅ Không phát hiện bất thường — Kinh doanh hoạt động ổn định</div>', unsafe_allow_html=True)

# ── CHARTS ────────────────────────────────────────────────────────────────────
ch1, ch2 = st.columns([3, 2])
with ch1:
    trend_title = kpi.get("trend_title", "📈 Xu Hướng Doanh Thu")
    st.markdown(f"**{trend_title}**")
    
    if st.session_state.mgr_period == "🗓️ Theo Tháng (Đủ Ngày)":
        if st.button("⬅️ Quay lại Mốc Năm 2007 (12 Tháng)", key="btn_back_year"):
            st.session_state.mgr_period = "🏢 Theo Năm (12 Tháng)"
            st.rerun()

    if kpi.get("trend"):
        df_t = pd.DataFrame(kpi["trend"])
        df_t["ngay"] = df_t["ngay"].astype(str)
        n = len(df_t)
        cols_bar = ["#38bdf8" if float(v) > 0 else "#334155" for v in df_t["rev"]]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_t["ngay"], y=df_t["rev"], marker_color=cols_bar, opacity=0.9, name="Doanh thu",
            text=[f"${v:,.0f}" if float(v) > 0 else "" for v in df_t["rev"]], textposition="auto",
            hovertemplate="<b>%{x}</b><br>Doanh thu: $%{y:,.2f}<extra></extra>"
        ))
        if n > 2 and any(float(v) > 0 for v in df_t["rev"]):
            fig.add_trace(go.Scatter(
                x=df_t["ngay"], y=df_t["rev"], mode="lines+markers",
                line=dict(color="#c084fc", width=2, dash="dot"), marker=dict(size=5), name="Xu hướng",
                hoverinfo="skip"
            ))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#94a3b8", size=11), showlegend=False,
                            bargap=0.25 if n > 12 else 0.35,
                            margin=dict(l=0,r=0,t=10,b=0), height=270,
                            xaxis=dict(type='category', showgrid=False, tickangle=-45 if n > 12 else 0),
                            yaxis=dict(showgrid=True, gridcolor="rgba(100,116,139,.15)", tickprefix="$"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


with ch2:
    st.markdown("**🎬 Top 5 Thể Loại Phim Thu Nhập Cao Nhất**")
    if kpi["cats"]:
        df_c = pd.DataFrame(kpi["cats"])
        palette = ["#38bdf8","#818cf8","#c084fc","#fb923c","#34d399"]
        fig2 = go.Figure(go.Bar(
            x=df_c["total_sales"].astype(float), y=df_c["category"], orientation="h",
            marker_color=palette[:len(df_c)],
            text=[f"${float(v):,.0f}" for v in df_c["total_sales"]], textposition="auto",
            hovertemplate="<b>%{y}</b><br>Tổng doanh thu: $%{x:,.2f}<extra></extra>"
        ))
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#94a3b8", size=11), showlegend=False,
                            bargap=0.25,
                            margin=dict(l=0,r=0,t=10,b=0), height=250,
                            xaxis=dict(showgrid=True, gridcolor="rgba(100,116,139,.15)", tickprefix="$"),
                            yaxis=dict(type='category', showgrid=False))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})


e1, e2 = st.columns(2)
with e1:
    if kpi["films"]:
        with st.expander("🎬 Top 5 Phim Doanh Thu Cao Nhất Hôm Nay"):
            df_f = pd.DataFrame(kpi["films"])
            df_f.columns = ["Tên Phim", "Doanh Thu ($)"]
            df_f["Doanh Thu ($)"] = df_f["Doanh Thu ($)"].apply(lambda x: f"${float(x):,.2f}")
            st.dataframe(df_f, use_container_width=True, hide_index=True)
with e2:
    if kpi["stores"]:
        with st.expander("🏪 So Sánh Doanh Thu Giữa Các Chi Nhánh"):
            df_s = pd.DataFrame(kpi["stores"])
            df_s.columns = ["Chi Nhánh", "Quản Lý", "Tổng Doanh Thu ($)"]
            df_s["Tổng Doanh Thu ($)"] = df_s["Tổng Doanh Thu ($)"].apply(lambda x: f"${float(x):,.2f}")
            st.dataframe(df_s, use_container_width=True, hide_index=True)

# ── STREAM MODE ───────────────────────────────────────────────────────────────
st.markdown('<div class="chat-hdr"><span style="font-size:1.2rem">💬</span> <span class="sec-title">STREAM MODE — Phân Tích Chuyên Sâu (AI Chat)</span><div style="color:#64748b;font-size:.76rem;margin-top:2px">Hỏi bất kỳ câu hỏi nào để phân tích dữ liệu chuyên sâu • Powered by LangGraph + Graph-RAG</div></div>', unsafe_allow_html=True)

suggs = build_suggestions(kpi, alerts)
st.markdown("**💡 Gợi ý câu hỏi dựa trên dữ liệu hôm nay:**")
sg_cols = st.columns(3)
sel_sug = None
for i, s in enumerate(suggs):
    with sg_cols[i % 3]:
        if st.button(f"💬 {s}", key=f"sg_{i}", use_container_width=True):
            sel_sug = s

st.markdown("---")

def render_demo_ui_sections(msg: dict):
    seed_tbls = msg.get("seed_tables") or []
    ret_tbls = msg.get("retrieved_tables") or []
    bridge_tbls = msg.get("bridge_tables") or [t for t in ret_tbls if t not in seed_tbls]
    sch_ctx = msg.get("schema_context", "")
    sql_o = msg.get("sql", "")
    df_res = msg.get("df")
    err = msg.get("err")
    ts = msg.get("ts", "0")
    lat = msg.get("lat")
    retry_cnt = msg.get("retry_count", 0)

    if err and df_res is None:
        st.error(err)
        if sql_o:
            with st.expander("🛠️ Xem chi tiết truy vấn SQL"):
                st.code(sql_o, language="sql")
        return

    # Section 1: Prompt 1 Output
    st.markdown("### 📌 1. Các Bảng Thực Thể Được Chọn (Prompt 1 Output)")
    if seed_tbls:
        for t in seed_tbls:
            st.markdown(f'<span class="badge-sel">📄 {t}</span>', unsafe_allow_html=True)
    else:
        st.caption("Không xác định bảng thực thể")
    st.markdown("<br>", unsafe_allow_html=True)

    # Section 2: OpenMetadata & GraphDB Output
    st.markdown("### 🌐 2. Bảng Kết Nối, Khóa Ngoại & Mô Tả Trực Tiếp Từ OpenMetadata")
    if bridge_tbls:
        st.markdown("**Bảng nối tự động bổ sung bởi GraphDB:**")
        for b in bridge_tbls:
            st.markdown(f'<span class="badge-conn">🔗 {b}</span>', unsafe_allow_html=True)

    if sch_ctx:
        with st.expander("📄 Chi tiết Schema Context Trích Xuất Từ OpenMetadata", expanded=False):
            st.code(sch_ctx, language="yaml")
    st.markdown("<br>", unsafe_allow_html=True)

    # Section 3: Prompt 2 Output
    st.markdown("### 💻 3. Câu Lệnh SQL PostgreSQL Sinh Ra (Prompt 2 Output)")
    if sql_o:
        st.code(sql_o, language="sql")
        if retry_cnt > 0:
            st.caption(f"🔄 Giai đoạn 5: Đã tự động sửa lỗi cú pháp qua Self-Correction Loop ({retry_cnt} lần)!")

    # Section 4: PostgreSQL Query Execution Results
    st.markdown("### 📊 4. Kết Quả Truy Vấn CSDL PostgreSQL")
    if df_res is not None and not df_res.empty:
        st.dataframe(df_res, use_container_width=True)
        st.download_button("📥 Xuất báo cáo CSV",
            data=df_res.to_csv(index=False).encode("utf-8"),
            file_name=f"bao_cao_{ts}.csv", mime="text/csv",
            key=f"dl_{ts}_{id(msg)}")
        if lat:
            st.caption(f"⏱️ {lat:.0f}ms | 📊 {len(df_res)} bản ghi")
    else:
        st.caption("ℹ️ Không có bản ghi nào được trả về.")


for msg in st.session_state.mgr_msgs:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(f"**{msg['content']}**")
        else:
            render_demo_ui_sections(msg)

prompt_in = st.chat_input("Nhập câu hỏi phân tích... (VD: Nhân viên nào có doanh thu cao nhất?)")
question = sel_sug or prompt_in

if question:
    st.session_state.mgr_msgs.append({"role": "user", "content": question})
    st.session_state.mgr_qcount += 1
    with st.chat_message("user"):
        st.markdown(f"**{question}**")

    with st.chat_message("assistant"):
        with st.status("🧠 Enterprise Text2SQL AI Agent đang xử lý qua 5 Giai đoạn...", expanded=True) as sb:
            st.write("1️⃣ **GIAI ĐOẠN 1**: Nhận câu hỏi & Kiểm tra Input Guardrail...")
            time.sleep(0.1)
            st.write("2️⃣ **GIAI ĐOẠN 2**: LLM phân tích ý định & chọn bảng thực thể chính (Prompt 1 + OpenMetadata Overview)...")
            time.sleep(0.1)
            st.write("3️⃣ **GIAI ĐOẠN 3**: GraphDB (NetworkX) tìm đường đi ngắn nhất nối bảng & Trích xuất Metadata chi tiết...")
            time.sleep(0.1)
            st.write("4️⃣ **GIAI ĐOẠN 4**: LLM sinh mã SQL PostgreSQL (Prompt 2 + Strict Foreign Keys)...")
            time.sleep(0.1)
            st.write("5️⃣ **GIAI ĐOẠN 5**: Kiểm tra bảo mật Read-Only & Tự động sửa lỗi cú pháp (Self-Correction)...")

            init_s = {
                "question": question, "schema_context": "", "sql": "",
                "risk_level": None, "risk_reason": None,
                "requires_approval": False, "is_blocked": False, "approval_status": None,
                "query_result": None, "error_message": None, "retry_count": 0, "max_retries": 3,
            }
            run_cfg = {"configurable": {"thread_id": f"mgr_{st.session_state.mgr_qcount}"}}
            lf = get_langfuse_handler()
            if lf: run_cfg["callbacks"] = [lf]

            t0 = time.perf_counter()
            fs = text2sql_agent_graph.invoke(init_s, config=run_cfg)
            lat = (time.perf_counter() - t0) * 1000
            st.session_state.mgr_lat = lat

            if lf:
                try:
                    flush_all()
                except Exception:
                    pass

            sb.update(label=f"✅ Hoàn thành quy trình 5 giai đoạn ({lat:.0f}ms)", state="complete", expanded=False)

        sql_o     = fs.get("sql", "")
        res       = fs.get("query_result")
        err       = fs.get("error_message")
        blk       = fs.get("is_blocked", False)
        seed_tbls = fs.get("seed_tables") or []
        ret_tbls  = fs.get("retrieved_tables") or []
        sch_ctx   = fs.get("schema_context", "")
        retry_cnt = fs.get("retry_count", 0)
        ts_now    = time.strftime("%Y%m%d_%H%M%S")
        df_res    = pd.DataFrame(res) if res and isinstance(res, list) and len(res) > 0 else None

        msg_data = {
            "role": "assistant",
            "seed_tables": seed_tbls,
            "retrieved_tables": ret_tbls,
            "bridge_tables": [t for t in ret_tbls if t not in seed_tbls],
            "schema_context": sch_ctx,
            "sql": sql_o,
            "df": df_res,
            "err": err if (blk or df_res is None or df_res.empty) else None,
            "lat": lat,
            "ts": ts_now,
            "retry_count": retry_cnt
        }

        render_demo_ui_sections(msg_data)
        st.session_state.mgr_msgs.append(msg_data)


