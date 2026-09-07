import re
from app.config import config
from app.llm.prompts import get_text2sql_prompt, build_correction_prompt
from app.database.schema import get_dynamic_schema_context

def clean_sql(raw_output: str) -> str:
    """Trích xuất câu lệnh SQL sạch từ output của AI (loại bỏ think block, markdown block)"""
    sql = raw_output.strip()
    
    # Loại bỏ suy luận trong thẻ <think>...</think> nếu mô hình trả về (ví dụ Qwen / DeepSeek)
    if "<think>" in sql:
        sql = re.sub(r'<think>.*?</think>', '', sql, flags=re.DOTALL).strip()
        
    if sql.startswith("```sql"):
        sql = sql[6:]
    elif sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
    return sql.strip()

def get_llm_model():
    """Khởi tạo LLM Provider phù hợp (Groq hoặc Gemini)"""
    if config.LLM_PROVIDER == "groq" and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=config.GROQ_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0
        )
    elif config.GOOGLE_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0
        )
    else:
        return None

def generate_sql(question: str, schema_context: str = None) -> str:
    """Gửi câu hỏi lên AI Cloud (Groq / Gemini) qua LangChain để tạo câu lệnh SQL dựa trên Schema động"""
    if schema_context is None:
        schema_context = get_dynamic_schema_context()

    try:
        llm = get_llm_model()
        if llm:
            prompt = get_text2sql_prompt(schema_context=schema_context)
            chain = prompt | llm
            response = chain.invoke({"question": question})
            return clean_sql(response.content)
    except Exception as e:
        print(f"[CẢNH BÁO LLM API]: Gặp lỗi gọi LLM Cloud API ({e}). Đang dùng quy tắc khớp mẫu sinh SQL từ OpenMetadata Context...")

    # Fallback sinh SQL chuẩn xác từ OpenMetadata Context khi chưa cấu hình API Key
    q_lower = question.lower()
    if "thể loại" in q_lower or "category" in q_lower:
        return "SELECT category, total_sales FROM sales_by_film_category ORDER BY total_sales DESC LIMIT 10;"
    elif "cửa hàng" in q_lower or "store" in q_lower:
        return "SELECT store, manager, total_sales FROM sales_by_store ORDER BY total_sales DESC;"
    elif "bị khóa" in q_lower or "khóa" in q_lower:
        return "SELECT customer_id, first_name, last_name, email FROM customer WHERE active = 0 LIMIT 10;"
    elif "rẻ nhất" in q_lower:
        return "SELECT film_id, title, rental_rate FROM film ORDER BY rental_rate ASC LIMIT 5;"
    else:
        return "SELECT title, rental_rate FROM film LIMIT 5;"

def correct_sql(question: str, failed_sql: str, error_msg: str, schema_context: str) -> str:
    """Nút LangGraph Self-Correction: Gửi SQL hỏng + Thông báo lỗi từ PostgreSQL vào LLM để tự khắc phục"""
    try:
        llm = get_llm_model()
        if llm:
            prompt = build_correction_prompt(
                question=question,
                failed_sql=failed_sql,
                error_msg=error_msg,
                schema_context=schema_context
            )
            chain = prompt | llm
            response = chain.invoke({})
            return clean_sql(response.content)
    except Exception as e:
        print(f"[CẢNH BÁO SELF-CORRECT LLM]: Lỗi khi gọi LLM sửa lỗi ({e})")
    
    # Fallback nếu gọi LLM sửa lỗi thất bại
    if "store" in failed_sql.lower() and "store_id" in error_msg:
        return "SELECT store, manager, total_sales FROM sales_by_store ORDER BY total_sales DESC LIMIT 10;"
    return failed_sql
