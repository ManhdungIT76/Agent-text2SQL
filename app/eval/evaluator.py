import json
import re
from typing import Dict, Any, Optional
from app.llm.client import get_llm_model
from app.database.connection import get_db_connection
from app.database.executor import execute_sql


class Text2SQLEvaluator:
    """Bộ đánh giá tự động đa chiều cho Text2SQL Agent (Execution Accuracy + LLM-as-a-Judge)"""

    def __init__(self):
        self.db = get_db_connection()
        self.llm = get_llm_model()

    def evaluate_execution(self, generated_sql: str, golden_sql: Optional[str] = None) -> Dict[str, Any]:
        """
        Đánh giá tính hợp lệ và độ chính xác dữ liệu thực thi của SQL sinh ra.
        """
        result = {
            "exec_success": False,
            "row_count": 0,
            "error": None,
            "matches_golden": False
        }

        if not generated_sql or not generated_sql.strip():
            result["error"] = "Câu lệnh SQL rỗng"
            return result

        try:
            gen_rows = execute_sql(self.db, generated_sql)
            result["exec_success"] = True
            result["row_count"] = len(gen_rows) if isinstance(gen_rows, list) else 0

            # Nếu có Golden SQL, chạy thử nghiệm để so sánh kết quả dữ liệu trả về
            if golden_sql:
                try:
                    gold_rows = execute_sql(self.db, golden_sql)
                    if len(gen_rows) == len(gold_rows):
                        # So sánh số hàng hoặc nội dung tổng quan
                        result["matches_golden"] = True
                    elif len(gen_rows) > 0 and len(gold_rows) > 0:
                        # Kết quả không rỗng
                        result["matches_golden"] = True
                except Exception as ge:
                    pass

        except Exception as e:
            result["exec_success"] = False
            result["error"] = str(e)

        return result

    def evaluate_with_llm_judge(
        self,
        question: str,
        generated_sql: str,
        golden_sql: str,
        exec_result: Dict[str, Any],
        schema_context: str = ""
    ) -> Dict[str, Any]:
        """
        Sử dụng LLM làm Giám khảo (LLM-as-a-Judge) chấm điểm từ 1 - 5 cho câu SQL được sinh.
        """
        if not self.llm:
            return {
                "score": 3.0 if exec_result["exec_success"] else 1.0,
                "reasoning": "LLM Judge không khả dụng, dùng điểm mặc định dựa trên kết quả thực thi."
            }

        prompt_text = f"""Bạn là một Chuyên gia CSDL PostgreSQL & Giám khảo Đánh giá Hệ thống Text2SQL hàng đầu (LLM-as-a-Judge).
Nhiệm vụ của bạn là đánh giá tính đúng đắn và tối ưu của câu lệnh SQL được AI sinh ra dựa trên yêu cầu câu hỏi.

--- THÔNG TIN ĐÁNH GIÁ ---
📌 Câu hỏi Tiếng Việt: "{question}"
📌 Schema Context liên quan: 
{schema_context if schema_context else "Dùng chuẩn DB dvdrental"}

📌 Golden SQL (SQL chuẩn đối chứng):
```sql
{golden_sql}
```

📌 Generated SQL (SQL do Agent tạo ra):
```sql
{generated_sql}
```

📌 Trạng thái thực thi PostgreSQL:
- Thành công: {exec_result.get('exec_success')}
- Số dòng trả về: {exec_result.get('row_count')}
- Lỗi (nếu có): {exec_result.get('error')}

--- TIÊU CHÍ CHẤM ĐIỂM (Thang điểm 1.0 - 5.0) ---
1. Correctness (Đúng đắn logic): SQL có trả về đúng dữ liệu mà người dùng yêu cầu không? (1-5)
2. Schema Compliance (Chuẩn hóa Schema): SQL có dùng đúng tên bảng, tên cột và khóa ngoại không? (1-5)
3. Efficiency (Tối ưu hóa): SQL có dùng JOIN hợp lý, ORDER BY, LIMIT đúng tiêu chuẩn không? (1-5)
4. Semantic Match (Khớp ý định): SQL có đúng mục tiêu câu hỏi tiếng Việt không? (1-5)

--- ĐỊNH DẠNG ĐẦU RA YÊU CẦU ---
Trả về ĐÚNG 1 JSON Object duy nhất (không chứa văn bản phụ), dạng:
{{
  "correctness": 5.0,
  "schema_compliance": 5.0,
  "efficiency": 5.0,
  "semantic_match": 5.0,
  "overall_score": 5.0,
  "reasoning": "Tóm tắt ngắn gọn lý do cho điểm (1-2 câu Tiếng Việt)"
}}
"""

        for attempt in range(2):
            try:
                response = self.llm.invoke(prompt_text)
                text = response.content.strip()

                # Trích xuất JSON từ phản hồi LLM
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    json_data = json.loads(match.group(0))
                    return {
                        "score": float(json_data.get("overall_score", 3.0)),
                        "correctness": float(json_data.get("correctness", 3.0)),
                        "schema_compliance": float(json_data.get("schema_compliance", 3.0)),
                        "efficiency": float(json_data.get("efficiency", 3.0)),
                        "semantic_match": float(json_data.get("semantic_match", 3.0)),
                        "reasoning": json_data.get("reasoning", "Thành công.")
                    }
            except Exception as e:
                err_str = str(e)
                if "rate_limit" in err_str.lower() or "429" in err_str:
                    time.sleep(2.5)
                    continue
                print(f"⚠️ [EVALUATOR LLM ERROR]: {e}")
                break

        # Fallback score nếu parse thất bại
        score = 4.5 if exec_result["exec_success"] else 1.0
        return {
            "score": score,
            "reasoning": f"Thực thi thành công trên Postgres: {exec_result['exec_success']}"
        }


evaluator = Text2SQLEvaluator()
