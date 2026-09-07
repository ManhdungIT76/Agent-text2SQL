import sys

# Đảm bảo UTF-8 cho stdout trên Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.metadata.openmetadata_client import om_client
from app.agent.graph import text2sql_agent_graph, get_langfuse_handler

def run_query(question: str):
    print("=" * 80)
    print(f"❓ [USER INPUT]: \"{question}\"")
    print("=" * 80)
    
    # Kích hoạt LangGraph Workflow (Graph-RAG -> Prompt v2.0 -> Postgres Execution -> Self-Correction)
    initial_state = {
        "question": question,
        "schema_context": "",
        "sql": "",
        "query_result": None,
        "error_message": None,
        "retry_count": 0,
        "max_retries": 3
    }

    # Truyền Langfuse Handler vào config nếu đã cấu hình Key
    run_config = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        run_config["callbacks"] = [langfuse_handler]
        print("📊 [LANGFUSE TRACING]: Kích hoạt Callback Tracing cho lượt chạy này.")

    final_state = text2sql_agent_graph.invoke(initial_state, config=run_config)

    print(f"\n✨ [CÂU LỆNH SQL CUỐI CÙNG]:\n>>> {final_state.get('sql')}\n")

    results = final_state.get("query_result")
    if results is not None:
        print(f"📊 [KẾT QUẢ TRẢ VỀ BẢNG DỮ LIỆU]:\n{results}")
    else:
        print(f"⚠️ [CẢNH BÁO THỰC THI]: Không thể lấy dữ liệu ({final_state.get('error_message')})")

    print("=" * 80 + "\n")

def main():
    print("\n🚀 [ENTERPRISE LANGGRAPH TEXT2SQL AGENT]: GRAPH-RAG + SELF-CORRECTION LOOP\n")
    
    # 1. Đảm bảo Local Disk Cache đã được tạo/đồng bộ
    om_client.load_local_cache()
    
    # 2. Danh sách câu hỏi thử nghiệm (Tối đa 2 câu để tiết kiệm quota & tăng tốc độ test)
    questions = [
        "Cho tôi xem báo cáo tổng doanh thu bán đĩa phân theo từng thể loại phim?",
        "Cho tôi danh sách các khách hàng có tài khoản đang bị khóa?"
    ]
    
    for q in questions:
        run_query(q)

if __name__ == "__main__":
    main()
