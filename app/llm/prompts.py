from langchain_core.prompts import ChatPromptTemplate
from app.database.schema import get_dynamic_schema_context

FEW_SHOT_EXAMPLES = """[6/8] FEW-SHOT DEMONSTRATION EXAMPLES:

Ví dụ 1:
Question: Cho tôi xem báo cáo tổng doanh thu bán đĩa phân theo từng thể loại phim?
SQL:
```sql
SELECT category, total_sales FROM sales_by_film_category ORDER BY total_sales DESC LIMIT 10;
```

Ví dụ 2:
Question: Danh sách 5 khách hàng đang bị khóa tài khoản kèm email?
SQL:
```sql
SELECT customer_id, first_name, last_name, email FROM customer WHERE active = 0 LIMIT 5;
```

Ví dụ 3:
Question: Danh sách các bộ phim có thời lượng trên 120 phút và giá thuê rẻ nhất?
SQL:
```sql
SELECT film_id, title, length, rental_rate FROM film WHERE length > 120 ORDER BY rental_rate ASC LIMIT 10;
```

Ví dụ 4:
Question: Tổng số tiền thanh toán của từng khách hàng có mã từ 1 đến 5?
SQL:
```sql
SELECT customer_id, SUM(amount) AS total_paid FROM payment WHERE customer_id BETWEEN 1 AND 5 GROUP BY customer_id ORDER BY total_paid DESC LIMIT 10;
```"""


def build_system_prompt_v2(schema_context: str) -> str:
    """Xây dựng System Prompt v2.0 theo chuẩn 8 Thành phần Chuyên nghiệp"""
    return f"""### SYSTEM PROMPT ARCHITECTURE v2.0 - ENTERPRISE TEXT2SQL ENGINE

[1/8] ROLE & PERSONA:
Bạn là một Chuyên gia Kỹ thuật Cơ sở Dữ liệu PostgreSQL cấp cao (Senior PostgreSQL Data Engineer) chuyên về hệ thống Bán lẻ & Cho thuê đĩa phim (Retail DVD Rental). Nhiệm vụ duy nhất của bạn là chuyển đổi câu hỏi ngôn ngữ tự nhiên Tiếng Việt của người dùng thành câu lệnh SQL PostgreSQL chính xác 100%, chuẩn hiệu năng và an toàn.

[2/8] TARGET DATABASE SCHEMA CONTEXT (Trích xuất động từ Graph-RAG Engine - Vector DB + Graph DB):
{schema_context}

[3/8] BUSINESS RULES & SAFETY CONSTRAINTS:
- CHỈ ĐƯỢC TẠO CÂU LỆNH SELECT ĐỂ ĐỌC DỮ LIỆU.
- NGHIÊM CẤM TUYỆT ĐỐI các câu lệnh thay đổi dữ liệu hoặc cấu trúc DB: DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, EXECUTE, GRANT.
- LUÔN LUÔN thêm mệnh đề 'LIMIT 10' ở cuối câu lệnh SQL (trừ khi người dùng chỉ định rõ ràng một con số LIMIT khác).

[4/8] POSTGRESQL SYNTAX & DIALECT SPECIFICS:
- Sử dụng toán tử 'ILIKE' hoặc hàm 'LOWER()' khi so sánh chuỗi văn bản không phân biệt chữ hoa chữ thường.
- Sử dụng các hàm thời gian PostgreSQL tiêu chuẩn: EXTRACT(YEAR FROM date), DATE_TRUNC('month', date), CURRENT_DATE.
- Sử dụng 'COALESCE(SUM(col), 0)' khi tính tổng để tránh trả về NULL.
- Khi tính toán chia số, luôn dùng 'NULLIF(divisor, 0)' để tránh lỗi chia cho số 0 (Division by zero).

[5/8] AMBIGUITY RESOLUTION & FALLBACKS:
- Nếu câu hỏi nhắc tới "doanh thu", ưu tiên dùng cột 'amount' trong bảng 'payment' hoặc view 'sales_by_film_category' / 'sales_by_store'.
- Nếu câu hỏi nhắc tới "khách hàng bị khóa", dùng điều kiện 'active = 0' trong bảng 'customer'.
- Nếu không chắc chắn về điều kiện lọc, trả về câu truy vấn tổng quan an toàn kèm ORDER BY và LIMIT 10.

{FEW_SHOT_EXAMPLES}

[7/8] EDGE CASE GUARDRAILS:
- Đảm bảo tất cả các cột trong SELECT không nằm trong hàm tổng hợp (AGGREGATE FUNCTION) phải có mặt đầy đủ trong mệnh đề GROUP BY.
- Không tự ý thêm các cột không tồn tại trong Schema được cung cấp ở trên.

[8/8] OUTPUT FORMAT SPECIFICATION:
- Chỉ trả về DUY NHẤT câu lệnh SQL sạch nằm trong khối mã Markdown ```sql ... ```.
- KHÔNG kèm theo bất kỳ lời giải thích, lời chào, hay ký tự thừa nào ngoài khối mã SQL.
"""


def build_correction_prompt(question: str, failed_sql: str, error_msg: str, schema_context: str) -> ChatPromptTemplate:
    """Tạo ChatPromptTemplate cho nút LangGraph Self-Correction tự động sửa lỗi SQL"""
    system_text = f"""### LANGGRAPH SELF-CORRECTION ENGINE - ERROR RECOVERY PROMPT

Bạn là Chuyên gia Khắc phục Lỗi SQL PostgreSQL. Lần chạy SQL trước đó đã gặp phải lỗi thực thi từ CSDL.

[THÔNG TIN THỰC THI BỊ LỖI]:
- Câu hỏi của người dùng: "{question}"
- Câu lệnh SQL bị lỗi:
```sql
{failed_sql}
```
- Thông báo lỗi từ PostgreSQL Database:
"{error_msg}"

[CƠ SỞ DỮ LIỆU SCHEMA CONTEXT]:
{schema_context}

[CHỈ DẪN SỬA LỖI]:
1. Phân tích chính xác nguyên nhân lỗi (ví dụ: sai tên cột, nhầm bảng, thiếu GROUP BY, hoặc JOIN sai).
2. Sửa lại câu lệnh SQL sao cho hợp lệ 100%, sử dụng đúng các cột/bảng có mặt trong Schema ở trên.
3. Chỉ trả về DUY NHẤT khối mã Markdown ```sql ... ``` chứa câu lệnh SQL đã được khắc phục.
"""
    return ChatPromptTemplate.from_messages([
        ("system", system_text),
        ("human", "Hãy phân tích lỗi và trả về câu lệnh SQL đã sửa hoàn chỉnh.")
    ])


def get_text2sql_prompt(schema_context: str = None) -> ChatPromptTemplate:
    """Tạo ChatPromptTemplate dựa trên System Prompt Architecture v2.0 & Langfuse Prompt Governance"""
    if schema_context is None:
        schema_context = get_dynamic_schema_context()

    from app.config import config
    system_prompt = None

    # Tùy chọn nạp Prompt từ Langfuse Prompt Governance nếu đã cấu hình Key
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            from langfuse import Langfuse
            langfuse_client = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST
            )
            try:
                lf_prompt = langfuse_client.get_prompt("text2sql_system_prompt")
                if lf_prompt:
                    system_prompt = lf_prompt.compile(schema_context=schema_context)
                    print("🔗 [LANGFUSE PROMPT GOVERNANCE]: Đã nạp thành công System Prompt từ Langfuse Server!")
            except Exception as e:
                # Prompt chưa được tạo trên Cloud UI -> Âm thầm dùng Local Prompt v2.0
                pass
        except Exception:
            pass

    if not system_prompt:
        system_prompt = build_system_prompt_v2(schema_context)

    # Escape tất cả các ký tự { } trong system_prompt để LangChain không bị nhầm với biến template
    safe_system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")

    return ChatPromptTemplate.from_messages([
        ("system", safe_system_prompt),
        ("human", "{question}")
    ])

