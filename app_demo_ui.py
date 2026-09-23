import sys
import warnings
import pandas as pd
import streamlit as st
import networkx as nx
import psycopg2

warnings.filterwarnings("ignore", message=".*use_container_width.*")

from app.agent.graph import text2sql_agent_graph, get_langfuse_handler
from app.metadata.openmetadata_client import om_client
from app.langfuse_utils import create_trace_handler, flush_all, check_langfuse_connection
from app.llm.prompts import TABLE_SELECTION_PROMPT_TEMPLATE, build_system_prompt_v2, get_display_prompt_text




if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Cấu hình Trang Streamlit
st.set_page_config(
    page_title="Text2SQL Demo Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS Tinh Gọn & Đẹp Mắt
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .compact-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e1e2f 100%);
        padding: 16px 20px;
        border-radius: 12px;
        border: 1px solid #334155;
        margin-bottom: 20px;
    }
    .compact-title {
        color: #38bdf8;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
    }
    .badge-sel {
        background-color: #0284c7;
        color: white;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 600;
        margin-right: 8px;
        display: inline-block;
    }
    .badge-conn {
        background-color: #d97706;
        color: white;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 600;
        margin-right: 8px;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# 🌐 NẠP DỮ LIỆU SCHEMA TRỰC TIẾP TỪ OPENMETADATA (OM CLIENT / CACHE)
# =====================================================================
om_data = om_client.load_local_cache()
om_tables = om_data.get("tables", {})

# 2. XÂY DỰNG ĐỒ THỊ GRAPHDB TỰ ĐỘNG THUẦN TỪ OPENMETADATA METADATA
DB_GRAPH = nx.Graph()
for t_name, tbl_info in om_tables.items():
    DB_GRAPH.add_node(t_name)
    for fk in tbl_info.get("foreign_keys", []):
        src_cols = ", ".join(fk.get("columns", []))
        target_tbl = fk.get("target_table", "")
        target_col = fk.get("target_column", "")
        if target_tbl and target_tbl in om_tables:
            DB_GRAPH.add_edge(
                t_name, 
                target_tbl, 
                fk=f"{t_name}.{src_cols} = {target_tbl}.{target_col}"
            )

# Cấu hình DB PostgreSQL kết nối thực tế
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "dvdrental",
    "user": "admin",
    "password": "password123"
}

# =====================================================================
# 3. ENRICH SCHEMA STEP 3 - TRÍCH XUẤT TRỰC TIẾP TỪ OPENMETADATA
# =====================================================================
def enrich_schema_step3(selected_tables: list):
    """Vá bảng nối qua GraphDB & rút trích Mô tả Cột + FK 100% trực tiếp từ OpenMetadata"""
    all_needed = set(selected_tables)
    bridge_tables = []
    fks = []

    valid_tables = [t for t in selected_tables if t in DB_GRAPH]

    if len(valid_tables) >= 2:
        for i in range(len(valid_tables)):
            for j in range(i + 1, len(valid_tables)):
                u, v = valid_tables[i], valid_tables[j]
                try:
                    if nx.has_path(DB_GRAPH, u, v):
                        path = nx.shortest_path(DB_GRAPH, u, v)
                        for node in path:
                            if node not in selected_tables and node not in bridge_tables:
                                bridge_tables.append(node)
                            all_needed.add(node)
                        for k in range(len(path) - 1):
                            edge_data = DB_GRAPH.get_edge_data(path[k], path[k+1])
                            if edge_data and "fk" in edge_data:
                                fks.append(edge_data["fk"])
                except (nx.NodeNotFound, nx.NetworkXNoPath):
                    pass

    # Xây dựng chuỗi Schema Context trực tiếp từ OpenMetadata Tables Data
    schema_lines = []
    for tbl_name in sorted(list(all_needed)):
        tbl_info = om_tables.get(tbl_name, {})
        t_desc = tbl_info.get("description", "Không có mô tả trong OpenMetadata.")
        cols_info = tbl_info.get("columns", [])
        
        cols_formatted = []
        for c in cols_info:
            c_name = c.get("name", "")
            c_type = c.get("type", "")
            c_desc = c.get("description", "")
            desc_part = f" - {c_desc}" if c_desc else ""
            cols_formatted.append(f"{c_name} ({c_type}){desc_part}")
        
        cols_str = "\n    - ".join(cols_formatted) if cols_formatted else "Không có cột"
        
        # Cảnh báo bảo vệ nếu bảng không có FK và có nhiều hơn 1 bảng trong context
        tbl_fks = tbl_info.get("foreign_keys", [])
        view_note = ""
        if not tbl_fks and len(all_needed) > 1 and "category" not in tbl_name:
            view_note = " ⚠️ [LƯU Ý: Bảng/View này KHÔNG có Khóa ngoại FK. KHÔNG JOIN bảng này với các bảng khác!]"
            
        schema_lines.append(f"• BẢNG `{tbl_name}`{view_note}:\n  Mô tả OM: {t_desc}\n  Các cột:\n    - {cols_str}")

    if fks:
        schema_lines.append(f"• KHÓA NGOẠI TRÍCH TỪ OPENMETADATA (FOREIGN KEYS):\n  - " + "\n  - ".join(set(fks)))

    return sorted(list(all_needed)), bridge_tables, list(set(fks)), "\n\n".join(schema_lines)


# --- HEADER TINH GỌN ---
from app.config import config

if config.LLM_PROVIDER == "groq" and config.GROQ_API_KEY:
    active_model_name = f"Groq Cloud ({config.GROQ_MODEL})"
elif config.GOOGLE_API_KEY:
    active_model_name = f"Google Gemini ({config.GEMINI_MODEL})"
else:
    active_model_name = "Rule-based Engine (Offline Fallback Mode)"

st.markdown(f"""
<div class="compact-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="compact-title">⚡ Text2SQL Demo Studio - Direct OpenMetadata Connected</div>
        <div style="background-color: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 0.9rem;">
            🤖 AI Model: {active_model_name}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# SIDEBAR SOI PROMPTS & OPENMETADATA STATUS
with st.sidebar:
    st.title("🌐 OpenMetadata & Prompts")
    if om_client.check_connection():
        st.success("🟢 OpenMetadata REST API (`http://localhost:8585`): Online Direct Sync")
    else:
        st.info("🟡 OpenMetadata: Đang dùng Disk Cache Local (`schema_cache.json`)")
        
    st.markdown(f"📊 **Tổng số bảng OpenMetadata**: `{len(om_tables)} Bảng`")

    # Hiển thị trạng thái Langfuse thực tế
    if check_langfuse_connection():
        st.success("🟢 Langfuse Cloud: Đã Kết Nối")
    else:
        from app.config import config
        if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
            st.info("🟡 Langfuse: Key đã cấu hình (chưa xác nhận kết nối)")
        else:
            st.warning("🔴 Langfuse: Chưa cấu hình API Key")
    
    if st.button("🔄 Đồng Bộ Metadata Mới", width="stretch"):
        with st.spinner("Đang làm mới RAM Cache từ OpenMetadata Server..."):
            om_client.reload_cache()
        st.success("✅ Đã làm mới Metadata trên RAM!")
        st.rerun()

    if st.button("🗑️ Xóa Lịch Sử Chat", width="stretch"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    
    prompt_1_display = get_display_prompt_text("text2sql-table-selector", TABLE_SELECTION_PROMPT_TEMPLATE)
    prompt_2_display = get_display_prompt_text("text2sql-generator", build_system_prompt_v2("{schema_context}"))

    with st.expander("📝 PROMPT 1 (text2sql-table-selector)"):
        st.code(prompt_1_display, language="markdown")
        
    with st.expander("💻 PROMPT 2 (text2sql-generator)"):
        st.code(prompt_2_display, language="markdown")



# QUẢN LÝ LỊCH SỬ CHAT TRONG SESSION STATE
if "messages" not in st.session_state:
    st.session_state.messages = []

# =====================================================================
# HIỂN THỊ CÁC CÂU HỎI & KẾT QUẢ XỬ LÝ TRƯỚC ĐÓ Ở PHÍA TRÊN
# =====================================================================
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message("user"):
        st.markdown(msg['question']) 

    with st.chat_message("assistant"):
        st.markdown(f"### 📌 1. Các Bảng Thực Thể Được Chọn (Prompt 1 Output)")
        for t in msg["selected_tables"]:
            st.markdown(f'<span class="badge-sel">📄 {t}</span>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("### 🌐 2. Bảng Kết Nối, Khóa Ngoại & Mô Tả Trực Tiếp Từ OpenMetadata")
        if msg["bridge_tables"]:
            st.markdown("**Bảng nối tự động bổ sung bởi GraphDB:**")
            for b in msg["bridge_tables"]:
                st.markdown(f'<span class="badge-conn">🔗 {b}</span>', unsafe_allow_html=True)

        if msg["fk_links"]:
            st.markdown("**Khóa ngoại trích xuất từ OpenMetadata (Foreign Keys):**")
            for fk in msg["fk_links"]:
                st.code(fk, language="sql")

        with st.expander("📄 Chi tiết Schema Context Trích Xuất Từ OpenMetadata", expanded=False):
            st.code(msg["schema_context"], language="yaml")

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("### 💻 3. Câu Lệnh SQL PostgreSQL Sinh Ra (Prompt 2 Output)")
        st.code(msg["sql_code"], language="sql")

        st.markdown("### 📊 Kết Quả Truy Vấn CSDL PostgreSQL")
        if msg.get("df") is not None and not msg["df"].empty:
            st.dataframe(msg["df"], width="stretch")
        elif msg.get("error_msg"):
            st.caption(msg["error_msg"])
        else:
            st.caption("ℹ️ Không có bản ghi nào được trả về.")

# =====================================================================
# Ô CHAT NHẬP CÂU HỎI Ở PHÍA DƯỚI (ST.CHAT_INPUT)
# =====================================================================
user_question = st.chat_input("💬 Nhập câu hỏi tra cứu dữ liệu (ví dụ: Cho tôi 5 diễn viên đóng nhiều phim nhất?)...")

if user_question:
    query_count = len(st.session_state.messages) + 1

    with st.spinner("⚡ [LangGraph State Machine Agent]: Đang thực thi qua 6 Nút (Graph-RAG -> Generator -> Safety Assessor -> PostgreSQL -> Self-Correction)..."):
        # Lọc sạch lịch sử chat: chỉ lấy question và sql_code (loại bỏ đối tượng DataFrame gây lỗi msgpack)
        clean_history = [
            {
                "role": "user", "question": m.get("question", ""),
                "role_assistant": "assistant", "sql": m.get("sql_code", "")
            }
            for m in st.session_state.messages
        ]

        initial_state = {
            "question": user_question,
            "chat_history": clean_history,
            "schema_context": "",
            "sql": "",
            "query_result": None,
            "error_message": None,
            "retry_count": 0,
            "max_retries": 3
        }

        run_config = {"configurable": {"thread_id": f"demo_ui_{query_count}"}}
        lf_handler = get_langfuse_handler(
            session_id=f"demo_ui_session_{query_count}",
            trace_name=f"demo-ui-query-{query_count}"
        )
        if lf_handler:
            run_config["callbacks"] = [lf_handler]

        final_state = text2sql_agent_graph.invoke(initial_state, config=run_config)
        flush_all()

    # Trích xuất dữ liệu từ trạng thái cuối (Final State) của LangGraph
    seed_tables = final_state.get("seed_tables") or []
    retrieved_tables = final_state.get("retrieved_tables") or []
    bridge_tables = [t for t in retrieved_tables if t not in seed_tables]
    schema_context = final_state.get("schema_context", "")
    sql_code = final_state.get("sql", "")
    query_result = final_state.get("query_result")
    err_text = final_state.get("error_message")

    result_df = pd.DataFrame(query_result) if query_result and isinstance(query_result, list) and len(query_result) > 0 else None

    # THÊM VÀO LỊCH SỬ CHAT SESSION STATE VÀ RERUN ĐỂ HIỂN THỊ
    st.session_state.messages.append({
        "question": user_question,
        "selected_tables": seed_tables,
        "bridge_tables": bridge_tables,
        "fk_links": [],
        "schema_context": schema_context,
        "sql_code": sql_code,
        "df": result_df,
        "error_msg": err_text
    })

    st.rerun()


