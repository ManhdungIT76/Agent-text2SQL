import re
from typing import Dict, Any
import sqlglot
from sqlglot import exp
from app.metadata.schema_retriever import schema_retriever
from app.llm.client import generate_sql, clean_sql, get_llm_model


class SchemaAnalystSubAgent:
    """Sub-Agent 1: Phân tích Ý định & Quản lý Schema Context (Bao gồm Table Selection LLM & GraphDB Expansion)"""

    def select_entity_tables(self, question: str) -> list:
        """Bước 2: Nạp schema_overview từ OpenMetadata -> Gọi LLM chọn danh sách bảng thực thể chính (seed_tables)"""
        print(f"[STEP 2: TABLE SELECTOR] Selecting entity tables via LLM...")
        from app.llm.client import select_tables
        from app.metadata.openmetadata_client import om_client
        overview = om_client.get_schema_overview()
        selected_tables = select_tables(question, schema_overview=overview)
        print(f"[STEP 2: TABLE SELECTOR] Selected tables -> {selected_tables}")
        return selected_tables

    def expand_schema_context(self, seed_tables: list):
        """Bước 3: Nhận seed_tables -> Dùng GraphDB NetworkX tìm bảng nối trung gian & trích xuất Schema Context chi tiết"""
        print(f"[STEP 3: GRAPH-RAG] Expanding schema context via GraphDB for {seed_tables}...")
        context, clean_seeds, all_needed = schema_retriever.get_schema_context_from_seed_tables_detailed(seed_tables)
        print(f"[STEP 3: GRAPH-RAG] Total required tables -> {all_needed}")
        return context, clean_seeds, all_needed

    def analyze_schema_detailed(self, question: str):
        """Hàm tương thích ngược (Backward compatibility)"""
        selected_tables = self.select_entity_tables(question)
        return self.expand_schema_context(selected_tables)


class SQLGeneratorSubAgent:
    """Sub-Agent 2: Sinh câu lệnh SQL PostgreSQL"""

    def generate(self, question: str, schema_context: str) -> str:
        print(f"[STEP 4: GENERATOR] Generating PostgreSQL query via LLM...")
        sql = generate_sql(question, schema_context=schema_context)
        return sql



class SafetyRiskSubAgent:
    """Sub-Agent 3: Phân tích & Kiểm soát Rủi ro CSDL bằng SQLGlot AST Parser (Chuẩn Enterprise)"""

    DISALLOWED_FUNCTIONS = {"pg_sleep", "pg_read_file", "pg_write_file", "dblink", "dblink_exec"}

    def evaluate_risk(self, question: str, sql: str) -> Dict[str, Any]:
        print(f"[STEP 5: SAFETY] Evaluating security policy via SQLGlot...")

        # 0. Bỏ qua nếu LLM từ chối (Anti-Hallucination)
        if "CANNOT_ANSWER" in sql.upper():
            reason = sql.replace("CANNOT_ANSWER:", "").strip()
            print(f"   [STEP 5: SAFETY] Assessment -> Out-of-Schema Refusal: {reason}")
            return {
                "risk_level": "LEVEL_1_SAFE",
                "is_blocked": True,
                "risk_reason": reason,
                "normalized_sql": sql,
                "error_message": None
            }

        # 1. KIỂM TRA CÚ PHÁP (Nhánh 6.3 - Cú pháp gãy nặng)
        try:
            parsed = sqlglot.parse_one(sql, read="postgres")
        except Exception as parse_err:
            reason = f"Lỗi cú pháp SQL (SQLGlot): {parse_err}"
            print(f"   [STEP 5: SAFETY] Syntax error detected: {parse_err}")
            return {
                "risk_level": "LEVEL_2_WARN",
                "is_blocked": False,
                "risk_reason": reason,
                "normalized_sql": sql,
                "error_message": reason
            }

        # 2. KIỂM TRA LỆNH CẤM DDL/DML (Nhánh 6.2 - Chặn luôn)
        is_select_query = isinstance(parsed, (exp.Select, exp.Union)) or getattr(parsed, "key", "") == "select"
        if not is_select_query:
            cmd_type = getattr(parsed, "key", "DML/DDL").upper()
            reason = f"CHẶN BẢO MẬT: Phát hiện câu lệnh thay đổi dữ liệu/cấu trúc ({cmd_type}). Chính sách Strict Read-Only được kích hoạt."
            print(f"   [STEP 5: SAFETY] BLOCKED: Unsafe DML/DDL command ({cmd_type})")
            return {
                "risk_level": "LEVEL_3_BLOCKED",
                "is_blocked": True,
                "risk_reason": reason,
                "normalized_sql": sql,
                "error_message": reason
            }

        # Kiểm tra hàm nguy hiểm (Injection / DoS)
        called_functions = {func.name.lower() for func in parsed.find_all(exp.Anonymous)}
        dangerous_calls = called_functions.intersection(self.DISALLOWED_FUNCTIONS)
        if dangerous_calls:
            reason = f"CHẶN BẢO MẬT: Phát hiện hàm cấm thực thi: {', '.join(dangerous_calls)}."
            print(f"   [STEP 5: SAFETY] BLOCKED: Disallowed function ({', '.join(dangerous_calls)})")
            return {
                "risk_level": "LEVEL_3_BLOCKED",
                "is_blocked": True,
                "risk_reason": reason,
                "normalized_sql": sql,
                "error_message": reason
            }

        # 3. TỰ ĐỘNG CHUẨN HÓA (Nhánh 6.1 - Tự vá trong RAM)
        has_limit = parsed.args.get("limit") is not None
        if not has_limit:
            parsed = parsed.limit(10)
            normalized_sql = parsed.sql(dialect="postgres", pretty=True)
            print(f"   [STEP 5: SAFETY] Auto-optimized: Injected LIMIT 10.")
            return {
                "risk_level": "LEVEL_1_SAFE",
                "is_blocked": False,
                "risk_reason": "Đã tự động bổ sung LIMIT 15.",
                "normalized_sql": normalized_sql,
                "error_message": None
            }

        print(f"   [STEP 5: SAFETY] Assessment -> SAFE (Strict Read-Only via SQLGlot)")
        return {
            "risk_level": "LEVEL_1_SAFE",
            "is_blocked": False,
            "risk_reason": "Truy vấn READ-ONLY an toàn.",
            "normalized_sql": parsed.sql(dialect="postgres", pretty=True),
            "error_message": None
        }



class IntentRouterSubAgent:
    """Sub-Agent 0: Phân luồng ý định người dùng (Intent Router) bằng LLM siêu nhẹ (PROMPT 0)"""

    def classify_intent(self, question: str) -> tuple[str, str]:
        print(f"\n================================================================================")
        print(f"[STEP 0: INTENT ROUTER] Đang gọi LLM phân loại ý định cho câu hỏi...")
        print(f"-> User Request: \"{question}\"")
        
        from app.llm.client import classify_intent
        intent, chat_resp = classify_intent(question)
        if intent == "chat":
            print(f"-> [KẾT QUẢ] Ý định: Giao tiếp xã giao (Chat)")
            print(f"-> [HÀNH ĐỘNG] Dừng luồng Graph-RAG, trả lời trực tiếp: {chat_resp}")
        else:
            print(f"-> [KẾT QUẢ] Ý định: Truy vấn CSDL (SQL)")
            print(f"-> [HÀNH ĐỘNG] Chuyển tiếp câu hỏi vào luồng LangGraph Text-to-SQL...")
        print(f"================================================================================\n")
        return intent, chat_resp



# Singletons
intent_router_agent = IntentRouterSubAgent()
schema_analyst_agent = SchemaAnalystSubAgent()
sql_generator_agent = SQLGeneratorSubAgent()
safety_risk_agent = SafetyRiskSubAgent()
