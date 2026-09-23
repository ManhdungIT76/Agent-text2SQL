import re
from typing import Dict, Any
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
    """Sub-Agent 2: Sinh câu lệnh SQL PostgreSQL chuyên sâu bằng System Prompt Architecture v2.0"""

    def generate(self, question: str, schema_context: str) -> str:
        print(f"[STEP 4: GENERATOR] Generating PostgreSQL query via LLM...")
        sql = generate_sql(question, schema_context=schema_context)
        return sql



class SafetyRiskSubAgent:
    """Sub-Agent 3: Phân tích & Kiểm soát Rủi ro An toàn CSDL (Strict Read-Only Enforcement)"""

    DANGEROUS_PATTERNS = [
        r'\bUPDATE\b', r'\bDELETE\b', r'\bDROP\b', r'\bALTER\b',
        r'\bTRUNCATE\b', r'\bINSERT\b', r'\bCREATE\b', r'\bGRANT\b', r'\bREVOKE\b'
    ]

    def evaluate_risk(self, question: str, sql: str) -> Dict[str, Any]:
        print(f"[STEP 5: SAFETY] Evaluating security policy...")
        sql_upper = sql.upper()
        q_upper = question.upper()

        # 1. Kiểm tra phát hiện từ khóa DML/DDL nguy hiểm -> CHẶN TUYỆT ĐỐI 100%
        detected_dangerous = []
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sql_upper) or re.search(pattern, q_upper):
                matched = pattern.replace(r'\b', '')
                detected_dangerous.append(matched)

        if detected_dangerous:
            reason = f"[STEP 5: SAFETY] BLOCKED: Detected unsafe DML command ({', '.join(set(detected_dangerous))}). Strict Read-Only policy enforced."
            print(f"   {reason}")
            return {
                "risk_level": "LEVEL_3_BLOCKED",
                "requires_approval": False,
                "is_blocked": True,
                "risk_reason": reason
            }

        # 2. Kiểm tra truy vấn quét dữ liệu rộng
        if "SELECT" in sql_upper and "LIMIT" not in sql_upper:
            reason = "CẢNH BÁO: Truy vấn SELECT không giới hạn số dòng (thiếu LIMIT)."
            print(f"   [STEP 5: SAFETY] Assessment -> WARN: Missing LIMIT clause.")
            return {
                "risk_level": "LEVEL_2_WARN",
                "requires_approval": False,
                "is_blocked": False,
                "risk_reason": reason
            }

        print(f"   [STEP 5: SAFETY] Assessment -> SAFE (Strict Read-Only)")
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
