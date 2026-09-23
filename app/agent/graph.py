from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from app.agent.sub_agents import schema_analyst_agent, sql_generator_agent, safety_risk_agent
from app.llm.client import correct_sql, contextualize_question
from app.database.connection import get_db_connection
from app.database.executor import execute_sql


class AgentState(TypedDict):
    question: str
    chat_history: Optional[list]
    schema_context: str
    seed_tables: Optional[list]
    retrieved_tables: Optional[list]
    sql: str
    risk_level: Optional[str]
    risk_reason: Optional[str]
    requires_approval: bool
    is_blocked: bool
    approval_status: Optional[str]  # "APPROVED", "REJECTED", "MODIFIED"
    query_result: Optional[Any]
    error_message: Optional[str]
    retry_count: int
    max_retries: int


# Step 1: Sub-Agent 1 (Query Contextualizer & Rewriter)
def contextualize_query_node(state: AgentState) -> dict:
    raw_question = state["question"]
    print("\n================================================================================")
    print(f"[USER QUERY] \"{raw_question}\"")
    print("================================================================================")
    history = state.get("chat_history") or []
    standalone_question = contextualize_question(raw_question, chat_history=history)
    return {"question": standalone_question}


# Step 2: Sub-Agent 2 (Intent & Table Selector)
def select_entity_tables_node(state: AgentState) -> dict:
    question = state["question"]
    seed_tables = schema_analyst_agent.select_entity_tables(question)
    return {"seed_tables": seed_tables}


# Step 3: Sub-Agent 3 (GraphDB Expansion & Context Enricher)
def expand_graph_schema_node(state: AgentState) -> dict:
    seed_tables = state.get("seed_tables") or []
    context, clean_seeds, retrieved_tables = schema_analyst_agent.expand_schema_context(seed_tables)
    return {
        "schema_context": context,
        "seed_tables": clean_seeds,
        "retrieved_tables": retrieved_tables
    }


# Step 4: Sub-Agent 4 (SQL Specialist Generator)
def generate_sql_node(state: AgentState) -> dict:
    question = state["question"]
    context = state["schema_context"]
    sql = sql_generator_agent.generate(question, schema_context=context)
    return {"sql": sql, "error_message": None}


# Step 5: Sub-Agent 5 (Safety & Risk Assessment)
def evaluate_safety_node(state: AgentState) -> dict:
    question = state["question"]
    sql = state["sql"]
    risk_info = safety_risk_agent.evaluate_risk(question, sql)
    return {
        "risk_level": risk_info["risk_level"],
        "requires_approval": risk_info["requires_approval"],
        "is_blocked": risk_info.get("is_blocked", False),
        "risk_reason": risk_info["risk_reason"]
    }


# Human-in-the-Loop Approval Controller
def human_approval_node(state: AgentState) -> dict:
    requires_appr = state.get("requires_approval", False)
    is_blocked = state.get("is_blocked", False)
    status = state.get("approval_status")

    if is_blocked:
        print(f"[STEP 5: SAFETY] BLOCKED: {state.get('risk_reason')}")
        return {"approval_status": "BLOCKED"}

    if requires_appr and not status:
        print("\n[HITL] Interrupting flow for admin approval...")
        user_response = interrupt({
            "type": "HUMAN_APPROVAL_REQUIRED",
            "question": state["question"],
            "sql": state["sql"],
            "risk_level": state.get("risk_level"),
            "risk_reason": state.get("risk_reason"),
            "message": "⚠️ CẢNH BÁO RỦI RO DỮ LIỆU! Bạn có đồng ý cho phép thực thi câu lệnh SQL này không? (y/n)"
        })

        res_str = str(user_response).strip().lower()
        if res_str in ["y", "yes", "approve", "1", "true"]:
            approved_status = "APPROVED"
            print("[HITL] Decision -> APPROVED")
        else:
            approved_status = "REJECTED"
            print("[HITL] Decision -> REJECTED")

        return {"approval_status": approved_status}

    return {}


# Step 6: Thực thi SQL trên PostgreSQL
def execute_sql_node(state: AgentState) -> dict:
    is_blocked = state.get("is_blocked", False)
    requires_appr = state.get("requires_approval", False)
    approval_status = state.get("approval_status")

    if is_blocked or approval_status == "BLOCKED":
        msg = f"[STEP 6: EXECUTE] Aborted: {state.get('risk_reason', 'Strict Read-Only policy enforced.')}"
        return {
            "query_result": None,
            "error_message": msg
        }

    if requires_appr and approval_status == "REJECTED":
        msg = "[STEP 6: EXECUTE] Aborted: Rejected by HITL administrator."
        return {
            "query_result": None,
            "error_message": msg
        }

    sql = state["sql"]
    db = get_db_connection()
    try:
        results = execute_sql(db, sql)
        row_count = len(results) if isinstance(results, list) else 0
        print(f"[STEP 6: EXECUTE] Query executed successfully on PostgreSQL ({row_count} rows returned).")
        return {"query_result": results, "error_message": None}
    except Exception as e:
        error_str = str(e)
        return {"query_result": None, "error_message": error_str}


# LangGraph Self-Correction Loop
def correct_sql_node(state: AgentState) -> dict:
    question = state["question"]
    failed_sql = state["sql"]
    error_msg = state["error_message"]
    context = state["schema_context"]
    retry_count = state.get("retry_count", 0) + 1
    err_line = error_msg.splitlines()[0] if error_msg else "Unknown DB error"

    print(f"[SELF-CORRECT] Retry {retry_count}/3 -> Error: {err_line}")

    fixed_sql = correct_sql(
        question=question,
        failed_sql=failed_sql,
        error_msg=error_msg,
        schema_context=context
    )
    print(f"[SELF-CORRECT] Fixed SQL -> {fixed_sql}")
    return {"sql": fixed_sql, "retry_count": retry_count, "error_message": None}


def should_continue_after_execution(state: AgentState) -> str:
    """Hàm rẽ nhánh sau khi thực thi SQL: kiểm tra lỗi thực thi để tự sửa hay kết thúc"""
    error_msg = state.get("error_message")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    requires_appr = state.get("requires_approval", False)
    is_blocked = state.get("is_blocked", False)
    approval_status = state.get("approval_status")

    # Nếu bị chính sách STRICT READ-ONLY chặn hoặc bị REJECT thì dừng luôn
    if is_blocked or approval_status in ["BLOCKED", "REJECTED"]:
        return END

    if error_msg and error_msg.strip():
        if retry_count < max_retries:
            return "correct_sql"
        else:
            print(f"[ERROR] Self-Correction exceeded max retries ({max_retries}/{max_retries}). Query execution aborted.")
            return END
    return END



def create_text2sql_graph(checkpointer: Optional[Any] = None):
    """Khởi tạo và biên dịch LangGraph StateGraph Workflow với Sub-Agents & HITL Checkpointer"""
    workflow = StateGraph(AgentState)

    # Thêm các Nút (Nodes)
    workflow.add_node("contextualize_query", contextualize_query_node)
    workflow.add_node("select_entity_tables", select_entity_tables_node)
    workflow.add_node("expand_graph_schema", expand_graph_schema_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("evaluate_safety", evaluate_safety_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("execute_sql", execute_sql_node)
    workflow.add_node("correct_sql", correct_sql_node)

    # Thiết lập Luồng thực thi (Edges)
    workflow.set_entry_point("contextualize_query")
    workflow.add_edge("contextualize_query", "select_entity_tables")
    workflow.add_edge("select_entity_tables", "expand_graph_schema")
    workflow.add_edge("expand_graph_schema", "generate_sql")
    workflow.add_edge("generate_sql", "evaluate_safety")
    workflow.add_edge("evaluate_safety", "human_approval")
    workflow.add_edge("human_approval", "execute_sql")


    # Thêm rẽ nhánh điều kiện sau Nút execute_sql
    workflow.add_conditional_edges(
        "execute_sql",
        should_continue_after_execution,
        {
            "correct_sql": "correct_sql",
            END: END
        }
    )
    workflow.add_edge("correct_sql", "execute_sql")

    # Sử dụng Checkpointer mặc định MemorySaver nếu không truyền
    cp = checkpointer or MemorySaver()
    return workflow.compile(checkpointer=cp)


def get_langfuse_handler(session_id=None, trace_name=None):
    """Khởi tạo CallbackHandler cho Langfuse Tracing & Observability (sử dụng Singleton Module)"""
    from app.langfuse_utils import create_trace_handler
    return create_trace_handler(
        session_id=session_id,
        trace_name=trace_name or "text2sql-agent",
        tags=["text2sql", "langgraph"]
    )



# Instance agent graph mặc định kèm InMemory checkpointer
memory_checkpointer = MemorySaver()
text2sql_agent_graph = create_text2sql_graph(checkpointer=memory_checkpointer)
