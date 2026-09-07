from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
from app.metadata.schema_retriever import schema_retriever
from app.llm.client import generate_sql, correct_sql
from app.database.connection import get_db_connection
from app.database.executor import execute_sql


class AgentState(TypedDict):
    question: str
    schema_context: str
    sql: str
    query_result: Optional[Any]
    error_message: Optional[str]
    retry_count: int
    max_retries: int


def retrieve_schema_node(state: AgentState) -> dict:
    """Nút 1: Lấy Schema ngữ cảnh động từ Graph-RAG Engine (Vector DB + Graph DB)"""
    question = state["question"]
    context = schema_retriever.get_relevant_schema_context(question, top_k=2)
    return {"schema_context": context}


def generate_sql_node(state: AgentState) -> dict:
    """Nút 2: Sinh câu lệnh SQL với System Prompt Architecture v2.0"""
    question = state["question"]
    context = state["schema_context"]
    sql = generate_sql(question, schema_context=context)
    return {"sql": sql, "error_message": None}


def execute_sql_node(state: AgentState) -> dict:
    """Nút 3: Thực thi câu lệnh SQL trên PostgreSQL Database"""
    sql = state["sql"]
    db = get_db_connection()
    try:
        results = execute_sql(db, sql)
        return {"query_result": results, "error_message": None}
    except Exception as e:
        error_str = str(e)
        return {"query_result": None, "error_message": error_str}


def correct_sql_node(state: AgentState) -> dict:
    """Nút 4: LangGraph Self-Correction - Đưa lỗi từ PostgreSQL vào LLM để tự khắc phục"""
    question = state["question"]
    failed_sql = state["sql"]
    error_msg = state["error_message"]
    context = state["schema_context"]
    retry_count = state.get("retry_count", 0) + 1

    print(f"\n🔄 [LANGGRAPH SELF-CORRECTION LOOP (Lần {retry_count})]:")
    print(f"   ⚠️ Lỗi gặp phải từ PostgreSQL:\n   >>> {error_msg.splitlines()[0] if error_msg else ''}")
    print(f"   🧠 Đang đưa Traceback lỗi vào LLM để tự động điều chỉnh SQL...")

    fixed_sql = correct_sql(
        question=question,
        failed_sql=failed_sql,
        error_msg=error_msg,
        schema_context=context
    )
    print(f"   ✨ [CÂU LỆNH SQL ĐÃ ĐƯỢC SỬA TỰ ĐỘNG]:\n   >>> {fixed_sql}\n")
    return {"sql": fixed_sql, "retry_count": retry_count, "error_message": None}


def should_continue(state: AgentState) -> str:
    """Hàm rẽ nhánh điều kiện: kiểm tra SQL có bị lỗi và còn lượt retry hay không"""
    error_msg = state.get("error_message")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if error_msg and error_msg.strip():
        if retry_count < max_retries:
            return "correct_sql"
        else:
            print(f"⚠️ [LANGGRAPH ALERT]: Đã thử tự động sửa lỗi quá {max_retries} lần nhưng chưa thành công.")
            return END
    return END


def create_text2sql_graph():
    """Khởi tạo và biên dịch LangGraph StateGraph Workflow"""
    workflow = StateGraph(AgentState)

    # Thêm các Nút (Nodes)
    workflow.add_node("retrieve_schema", retrieve_schema_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("execute_sql", execute_sql_node)
    workflow.add_node("correct_sql", correct_sql_node)

    # Thiết lập Luồng thực thi (Edges)
    workflow.set_entry_point("retrieve_schema")
    workflow.add_edge("retrieve_schema", "generate_sql")
    workflow.add_edge("generate_sql", "execute_sql")

    # Thêm rẽ nhánh điều kiện tại Nút execute_sql
    workflow.add_conditional_edges(
        "execute_sql",
        should_continue,
        {
            "correct_sql": "correct_sql",
            END: END
        }
    )
    workflow.add_edge("correct_sql", "execute_sql")

    return workflow.compile()


def get_langfuse_handler():
    """Khởi tạo CallbackHandler cho Langfuse Tracing & Observability"""
    from app.config import config
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            from langfuse.callback import CallbackHandler
            return CallbackHandler(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST
            )
        except Exception as e:
            print(f"⚠️ [LANGFUSE ERROR]: Không thể khởi tạo CallbackHandler ({e})")
    return None


text2sql_agent_graph = create_text2sql_graph()

