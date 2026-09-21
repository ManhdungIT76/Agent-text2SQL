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
- LUÔN LUÔN thêm mệnh đề 'LIMIT 10' ở cuối câu lệnh SQL nhưng nếu có yêu cầu số lượng cụ thể thì hãy theo yêu cầu người dùng nhưng limit <= 15.

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


TABLE_SELECTION_PROMPT_TEMPLATE = """### SYSTEM PROMPT ARCHITECTURE - TABLE SELECTION AGENT

Bạn là một Chuyên gia Phân tích CSDL PostgreSQL. Nhiệm vụ của bạn là đọc câu hỏi của người dùng và chọn ra danh sách các BẢNG THỰC THỂ CHÍNH có trong CSDL phục vụ cho việc truy vấn.

[DANH MỤC BẢNG CSDL THỰC TẾ TRÍCH TỪ OPENMETADATA (SCHEMA OVERVIEW)]:
{schema_overview}

[QUY TẮC CHỌN BẢNG BẮT BUỘC]:
1. CHỈ ĐƯỢC CHỌN TÊN BẢNG CÓ NẰM TRONG DANH MỤC [SCHEMA OVERVIEW] Ở TRÊN.
2. TUYỆT ĐỐI KHÔNG TỰ BỊA ĐẶT HOẶC SUY ĐOÁN TÊN BẢNG KHÔNG CÓ TRONG DANH MỤC (Ví dụ: CƠ SỞ DỮ LIỆU KHÔNG CÓ BẢNG 'branches' HAY 'sales', KHÔNG DÙNG 'branches' THAY CHO 'store', KHÔNG DÙNG 'sales' THAY CHO 'payment').
3. Chỉ chọn các bảng thực thể chính chứa dữ liệu trực tiếp phục vụ câu hỏi.
4. KHÔNG tự suy đoán các bảng nối trung gian (Hệ thống GraphDB sẽ tự động bổ sung bảng nối và khóa ngoại ở bước tiếp theo).
5. TRẢ VỀ DUY NHẤT một chuỗi hợp lệ định dạng JSON Array chứa danh sách các tên bảng.
   Ví dụ định dạng đầu ra: ["table_1", "table_2"]
"""


CORRECTION_PROMPT_TEMPLATE = """### LANGGRAPH SELF-CORRECTION ENGINE - ERROR RECOVERY PROMPT

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


def _get_prompt_content(prompt_name: str, fallback_template: str, variables: dict = None) -> str:
    """
    Hàm nội bộ nạp Prompt từ Langfuse Prompt Governance theo đúng tên đăng ký trên Langfuse Cloud.
    Hỗ trợ Label, Version & Fallback về Local Prompt.
    Sử dụng Langfuse Singleton Client (không tạo client mới mỗi lần gọi).

    LƯU Ý QUAN TRỌNG:
    - Langfuse SDK compile() thay thế biến theo cú pháp {{variable}} (hai dấu ngoặc).
    - Nếu prompt Langfuse dùng cú pháp {variable} (một dấu ngoặc, kiểu Python),
      compile() sẽ bỏ qua → biến schema_overview/schema_context không được điền.
    - Hàm này xử lý cả hai trường hợp: sau compile(), nếu vẫn còn {variable} chưa thay,
      sẽ tự động thay thế bằng Python string replace.
    """
    if variables is None:
        variables = {}

    from app.config import config
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            from app.langfuse_utils import get_langfuse_client
            langfuse_client = get_langfuse_client()
            if langfuse_client:
                get_kwargs = {}
                lbl = getattr(config, "LANGFUSE_PROMPT_LABEL", "")
                ver = getattr(config, "LANGFUSE_PROMPT_VERSION", "")
                if lbl:
                    get_kwargs["label"] = lbl
                if ver:
                    get_kwargs["version"] = ver

                lf_prompt = langfuse_client.get_prompt(prompt_name, **get_kwargs)
                if lf_prompt:
                    # Bước 1: Langfuse compile() thay thế {{variable}} (cú pháp Langfuse)
                    compiled = lf_prompt.compile(**variables)

                    # Bước 2: Thay thế thêm {variable} (cú pháp Python) nếu còn sót
                    # Đây là nguyên nhân gốc khiến schema_overview/schema_context bị rỗng
                    for var_name, var_value in variables.items():
                        placeholder = "{" + var_name + "}"
                        if placeholder in compiled and var_value:
                            compiled = compiled.replace(placeholder, str(var_value))

                    try:
                        print(f"🔗 [LANGFUSE PROMPT GOVERNANCE]: Đã nạp thành công '{prompt_name}' từ Langfuse Server!")
                    except Exception:
                        print(f"[LANGFUSE PROMPT GOVERNANCE]: Da nap thanh cong '{prompt_name}' tu Langfuse Server!")
                    return compiled
        except Exception as e:
            try:
                print(f"⚠️ [LANGFUSE PROMPT WARN]: Không nạp được '{prompt_name}' từ Langfuse Cloud ({e}) → Dùng Local Fallback.")
            except Exception:
                print(f"[LANGFUSE PROMPT WARN]: Khong nap duoc '{prompt_name}' ({e}) -> Dung Local Fallback.")


def get_display_prompt_text(prompt_name: str, fallback_template: str) -> str:
    """Lấy trực tiếp văn bản Prompt từ Langfuse Server (hoặc local fallback) để hiển thị trên UI Sidebar"""
    from app.config import config
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            from app.langfuse_utils import get_langfuse_client
            langfuse_client = get_langfuse_client()
            if langfuse_client:
                get_kwargs = {}
                lbl = getattr(config, "LANGFUSE_PROMPT_LABEL", "")
                ver = getattr(config, "LANGFUSE_PROMPT_VERSION", "")
                if lbl:
                    get_kwargs["label"] = lbl
                if ver:
                    get_kwargs["version"] = ver

                lf_prompt = langfuse_client.get_prompt(prompt_name, **get_kwargs)
                if lf_prompt and hasattr(lf_prompt, "prompt"):
                    return str(lf_prompt.prompt)
        except Exception as e:
            print(f"[LANGFUSE DISPLAY WARN]: ({e}) -> Fallback local prompt")
    return fallback_template






def get_table_selection_prompt(schema_overview: str) -> ChatPromptTemplate:
    """PROMPT 1 (Giai đoạn 2): Nạp 'text2sql-table-selector' từ Langfuse Server"""
    system_prompt = _get_prompt_content(
        prompt_name="text2sql-table-selector",
        fallback_template=TABLE_SELECTION_PROMPT_TEMPLATE,
        variables={"schema_overview": schema_overview}
    )
    safe_text = system_prompt.replace("{", "{{").replace("}", "}}")
    return ChatPromptTemplate.from_messages([
        ("system", safe_text),
        ("human", "{question}")
    ])


def get_text2sql_prompt(schema_context: str = None) -> ChatPromptTemplate:
    """PROMPT 2 (Giai đoạn 4): Nạp 'text2sql-generator' từ Langfuse Server"""
    if schema_context is None:
        schema_context = get_dynamic_schema_context()

    fallback_sys = build_system_prompt_v2(schema_context)
    system_prompt = _get_prompt_content(
        prompt_name="text2sql-generator",
        fallback_template=fallback_sys,
        variables={"schema_context": schema_context}
    )
    safe_text = system_prompt.replace("{", "{{").replace("}", "}}")
    return ChatPromptTemplate.from_messages([
        ("system", safe_text),
        ("human", "{question}")
    ])


def build_correction_prompt(question: str, failed_sql: str, error_msg: str, schema_context: str) -> ChatPromptTemplate:
    """PROMPT 3 (Giai đoạn 5): Nạp 'text2sql-self-corrector' từ Langfuse Server"""
    system_text = _get_prompt_content(
        prompt_name="text2sql-self-corrector",
        fallback_template=CORRECTION_PROMPT_TEMPLATE,
        variables={
            "question": question,
            "failed_sql": failed_sql,
            "error_msg": error_msg,
            "schema_context": schema_context
        }
    )
    safe_text = system_text.replace("{", "{{").replace("}", "}}")
    return ChatPromptTemplate.from_messages([
        ("system", safe_text),
        ("human", "Hãy phân tích lỗi và trả về câu lệnh SQL đã sửa hoàn chỉnh.")
    ])

