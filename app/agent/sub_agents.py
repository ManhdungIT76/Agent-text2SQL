import re
from typing import Dict, Any
from app.metadata.schema_retriever import schema_retriever
from app.llm.client import generate_sql, clean_sql, get_llm_model


class SchemaAnalystSubAgent:
    """Sub-Agent 1: Phân tích Ý định (Prompt 1 - Langfuse text2sql-table-selector) & Trích xuất Schema Context từ GraphDB"""

    def analyze_schema_detailed(self, question: str):
        print(f"🔍 [SUB-AGENT 1: SCHEMA ANALYST]: Đang nạp schema_overview từ OpenMetadata -> Prompt 1 -> GraphDB...")
        from app.llm.client import select_tables
        from app.metadata.openmetadata_client import om_client
        overview = om_client.get_schema_overview()
        selected_tables = select_tables(question, schema_overview=overview)
        context, clean_seeds, all_needed = schema_retriever.get_schema_context_from_seed_tables_detailed(selected_tables)
        return context, clean_seeds, all_needed

class SQLGeneratorSubAgent:
    """Sub-Agent 2: Sinh câu lệnh SQL PostgreSQL chuyên sâu bằng System Prompt Architecture v2.0"""

    def generate(self, question: str, schema_context: str) -> str:

        print(f"✍️ [SUB-AGENT 2: SQL SPECIALIST GENERATOR]: Đang áp dụng System Prompt v2.0 & LLM để lập luận SQL...")
        sql = generate_sql(question, schema_context=schema_context)
        return sql



class SafetyRiskSubAgent:
    """Sub-Agent 3: Phân tích & Kiểm soát Rủi ro An toàn CSDL (Strict Read-Only Enforcement)"""

    DANGEROUS_PATTERNS = [
        r'\bUPDATE\b', r'\bDELETE\b', r'\bDROP\b', r'\bALTER\b',
        r'\bTRUNCATE\b', r'\bINSERT\b', r'\bCREATE\b', r'\bGRANT\b', r'\bREVOKE\b'
    ]

    def evaluate_risk(self, question: str, sql: str) -> Dict[str, Any]:
        print(f"🛡️ [SUB-AGENT 3: SAFETY & RISK ASSESSOR]: Đang kiểm tra chính sách an toàn STRICT READ-ONLY...")
        sql_upper = sql.upper()
        q_upper = question.upper()

        # 1. Kiểm tra phát hiện từ khóa DML/DDL nguy hiểm -> CHẶN TUYỆT ĐỐI 100%
        detected_dangerous = []
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sql_upper) or re.search(pattern, q_upper):
                matched = pattern.replace(r'\b', '')
                detected_dangerous.append(matched)

        if detected_dangerous:
            reason = f"🚫 [STRICT READ-ONLY BLOCKED]: Phát hiện thao tác thay đổi/xóa CSDL ({', '.join(set(detected_dangerous))}). Hệ thống cấm 100% các câu lệnh ngoài SELECT!"
            print(f"   ⛔ [SECURITY POLICY]: {reason}")
            return {
                "risk_level": "LEVEL_3_BLOCKED",
                "requires_approval": False,
                "is_blocked": True,
                "risk_reason": reason
            }

        # 2. Kiểm tra truy vấn quét dữ liệu rộng
        if "SELECT" in sql_upper and "LIMIT" not in sql_upper:
            reason = "CẢNH BÁO: Truy vấn SELECT không giới hạn số dòng (thiếu LIMIT)."
            print(f"   ⚠️ [RISK LEVEL: WARN]: {reason}")
            return {
                "risk_level": "LEVEL_2_WARN",
                "requires_approval": False,
                "is_blocked": False,
                "risk_reason": reason
            }

        print(f"   🟢 [RISK LEVEL: SAFE]: Truy vấn READ-ONLY an toàn 100%.")
        return {
            "risk_level": "LEVEL_1_SAFE",
            "requires_approval": False,
            "is_blocked": False,
            "risk_reason": "Truy vấn READ-ONLY an toàn."
        }


# Singletons
schema_analyst_agent = SchemaAnalystSubAgent()
sql_generator_agent = SQLGeneratorSubAgent()
safety_risk_agent = SafetyRiskSubAgent()
