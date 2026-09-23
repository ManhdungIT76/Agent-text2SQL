import re
from app.config import config
from app.llm.prompts import get_text2sql_prompt, build_correction_prompt
from app.database.schema import get_dynamic_schema_context

def clean_sql(raw_output) -> str:
    """Trích xuất câu lệnh SQL sạch từ output của AI (loại bỏ think block, markdown block, văn bản giải thích)"""
    if isinstance(raw_output, list):
        sql = " ".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in raw_output]).strip()
    else:
        sql = str(raw_output).strip()
    
    # 1. Loại bỏ suy luận trong thẻ <think>...</think> nếu mô hình trả về (ví dụ Qwen / DeepSeek)
    if "<think>" in sql:
        sql = re.sub(r'<think>.*?</think>', '', sql, flags=re.DOTALL).strip()
        
    # 2. Trích xuất khối mã Markdown ```sql ... ``` nếu có
    sql_match = re.search(r'```(?:sql)?\s*((?:WITH|SELECT).*?)```', sql, re.DOTALL | re.IGNORECASE)
    if sql_match:
        sql = sql_match.group(1).strip()
    else:
        # 3. Tìm từ câu lệnh WITH hoặc SELECT đầu tiên nếu không có khối markdown
        select_match = re.search(r'\b((?:WITH|SELECT)\b.*)', sql, re.DOTALL | re.IGNORECASE)
        if select_match:
            sql = select_match.group(1).strip()

    # Dọn dẹp ký tự markdown còn sót
    if sql.startswith("```sql"):
        sql = sql[6:]
    elif sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]

    sql = sql.strip()
    if sql and not sql.endswith(";"):
        sql += ";"

    return sql

def _get_langfuse_config():
    """Tự động lấy CallbackHandler của Langfuse để ghi vết (Tracing) mọi cuộc gọi LLM (Singleton)"""
    try:
        from app.langfuse_utils import create_trace_handler
        handler = create_trace_handler(trace_name="text2sql-llm-call", tags=["text2sql", "llm-call"])
        if handler:
            return {"callbacks": [handler]}, handler
    except Exception:
        pass
    return {}, None

def _flush_langfuse(handler):
    """Đánh dấu handler để flush sau (không flush ngay tại mỗi LLM call để tránh tăng latency).
    Caller (app_demo_ui, app_manager, app_streamlit) sẽ gọi flush_all() cuối pipeline."""
    # Langfuse SDK có auto-flush background thread.
    # flush_all() trong langfuse_utils sẽ flush toàn bộ handlers cuối pipeline.
    pass

def _validate_and_normalize_selected_tables(tables_list: list, question: str = "") -> list:
    """Lọc và chuẩn hóa danh sách bảng do LLM chọn (loại bỏ khoảng trắng, dấu ngoặc kép, ký tự thừa)."""
    if not isinstance(tables_list, list):
        return []
    cleaned = []
    for t in tables_list:
        if isinstance(t, str):
            clean_name = t.strip().strip('"').strip("'").strip("`").lower()
            if clean_name and clean_name not in cleaned:
                cleaned.append(clean_name)
    return cleaned

def select_tables(question: str, schema_overview: str) -> list:
    """Gửi câu hỏi + Schema Overview vào LLM THẬT (Groq / Gemini) với Prompt 1 để trả về mảng JSON tên các bảng chính."""
    from app.llm.prompts import get_table_selection_prompt
    import json

    prompt = get_table_selection_prompt(schema_overview=schema_overview)
    cfg, lf_handler = _get_langfuse_config()

    # Thử với Primary LLM
    try:
        llm = get_llm_model()
        if llm:
            chain = prompt | llm
            response = chain.invoke({"question": question}, config=cfg)
            _flush_langfuse(lf_handler)
            content = getattr(response, "content", response)
            raw_content = " ".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content]).strip() if isinstance(content, list) else str(content).strip()
            raw_content = re.sub(r'```(?:json)?\s*', '', raw_content, flags=re.IGNORECASE).replace('```', '').strip()
            json_match = re.search(r'\[.*?\]', raw_content, re.DOTALL)
            if json_match:
                raw_content = json_match.group(0)
            tables_list = json.loads(raw_content)
            if isinstance(tables_list, list):
                return _validate_and_normalize_selected_tables(tables_list, question=question)
    except Exception as e:
        print(f"[LLM WARN] Table selection primary model error ({e}) -> Switching to failover model...")

    # Thử với Fallback LLM nếu Primary bị Rate Limit (429)
    try:
        fallback_llm = get_fallback_llm()
        if fallback_llm:
            chain = prompt | fallback_llm
            response = chain.invoke({"question": question}, config=cfg)
            _flush_langfuse(lf_handler)
            content = getattr(response, "content", response)
            raw_content = " ".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content]).strip() if isinstance(content, list) else str(content).strip()
            raw_content = re.sub(r'```(?:json)?\s*', '', raw_content, flags=re.IGNORECASE).replace('```', '').strip()
            json_match = re.search(r'\[.*?\]', raw_content, re.DOTALL)
            if json_match:
                raw_content = json_match.group(0)
            tables_list = json.loads(raw_content)
            if isinstance(tables_list, list):
                print("[LLM INFO] Table selection failover model execution successful.")
                return _validate_and_normalize_selected_tables(tables_list, question=question)
    except Exception as fe:
        print(f"[LLM WARN] Table selection failover error ({fe}) -> Using rule-based fallback.")

    
    # Fallback tự động động 100%: Phân tích keyword từ schema_overview thay vì hardcode tên bảng
    parsed_tables = re.findall(r'• BẢNG `([^`]+)`', schema_overview)
    if not parsed_tables:
        parsed_tables = re.findall(r'\b([a-zA-Z0-9_]+)\b', schema_overview)
    
    q_words = set(question.lower().split())
    matched = []
    for tbl in parsed_tables:
        tbl_lower = tbl.lower()
        if tbl_lower in q_words or any(w in tbl_lower for w in q_words if len(w) > 3):
            matched.append(tbl)
    
    if matched:
        return _validate_and_normalize_selected_tables(matched, question=question)
    return _validate_and_normalize_selected_tables(parsed_tables[:3] if parsed_tables else [], question=question)



def get_llm_model():
    """Khởi tạo LLM Provider chính (Groq, Gemini hoặc HuggingFace theo cấu hình LLM_PROVIDER)"""
    if config.LLM_PROVIDER == "huggingface" and config.HUGGINGFACEHUB_API_TOKEN:
        try:
            from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
            endpoint = HuggingFaceEndpoint(
                repo_id=config.HUGGINGFACE_MODEL,
                huggingfacehub_api_token=config.HUGGINGFACEHUB_API_TOKEN,
                task="conversational",
                temperature=0.01,
                max_new_tokens=512
            )
            return ChatHuggingFace(llm=endpoint)
        except Exception as e:
            print(f"[LLM WARN] HuggingFace load error ({e}) -> Fallback to Groq/Gemini.")
            return get_fallback_llm()
    elif config.LLM_PROVIDER == "groq" and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=config.GROQ_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0,
            max_tokens=512
        )
    elif config.GOOGLE_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL,
            google_api_key=config.GOOGLE_API_KEY
        )
    else:
        return get_fallback_llm()

def get_fallback_llm():
    """Trả về Groq, Gemini hoặc Hugging Face làm LLM dự phòng khi Primary bị lỗi"""
    current = config.LLM_PROVIDER.lower()
    
    # 1. Thử Groq nếu chưa dùng Groq làm Primary
    if current != "groq" and config.GROQ_API_KEY:
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=config.GROQ_MODEL,
                api_key=config.GROQ_API_KEY,
                temperature=0,
                max_tokens=512
            )
        except Exception:
            pass

    # 2. Thử Gemini nếu chưa dùng Gemini làm Primary
    if current != "gemini" and config.GOOGLE_API_KEY:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=config.GEMINI_MODEL,
                google_api_key=config.GOOGLE_API_KEY
            )
        except Exception:
            pass

    # 3. Thử Hugging Face Inference Endpoint nếu chưa dùng Hugging Face làm Primary
    if current != "huggingface" and config.HUGGINGFACEHUB_API_TOKEN:
        try:
            from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
            endpoint = HuggingFaceEndpoint(
                repo_id=config.HUGGINGFACE_MODEL,
                huggingfacehub_api_token=config.HUGGINGFACEHUB_API_TOKEN,
                task="conversational",
                temperature=0.01,
                max_new_tokens=512
            )
            return ChatHuggingFace(llm=endpoint)
        except Exception:
            pass

    return None


def _is_rate_limit_error(err_str: str) -> bool:
    """Kiểm tra xem lỗi có phải do rate limit / quota vượt mức không"""
    err_lower = err_str.lower()
    return "429" in err_str or "413" in err_str or "rate_limit" in err_lower or "quota" in err_lower

def generate_sql(question: str, schema_context: str = None) -> str:
    """Gửi câu hỏi lên AI Cloud (Groq / Gemini) qua LangChain để tạo câu lệnh SQL dựa trên Schema động (Prompt 2)"""
    if schema_context is None:
        schema_context = get_dynamic_schema_context(question)

    prompt = get_text2sql_prompt(schema_context=schema_context)
    cfg, lf_handler = _get_langfuse_config()

    # Bước 1: Thử với LLM chính (Groq / Gemini theo cấu hình)
    try:
        llm = get_llm_model() or get_fallback_llm()
        if llm:
            chain = prompt | llm
            response = chain.invoke({"question": question}, config=cfg)
            _flush_langfuse(lf_handler)
            return clean_sql(response.content)
    except Exception as e:
        err_str = str(e)
        if _is_rate_limit_error(err_str):
            print(f"[LLM WARN] Primary model rate limited (429) -> Switching to failover...")
        else:
            print(f"[LLM WARN] Primary model error -> Switching to failover...")
            
        try:
            fallback_llm = get_fallback_llm()
            if fallback_llm:
                chain = prompt | fallback_llm
                response = chain.invoke({"question": question}, config=cfg)
                _flush_langfuse(lf_handler)
                print("[LLM INFO] Failover model execution successful.")
                return clean_sql(response.content)
        except Exception as fe:
            print(f"[LLM ERROR] Failover model failed: {fe}")
            
    raise RuntimeError("Không thể kết nối đến LLM Service (Groq/Gemini). Vui lòng kiểm tra lại API Key hoặc hạn mức Quota trong file .env.")



def correct_sql(question: str, failed_sql: str, error_msg: str, schema_context: str) -> str:
    """Nút LangGraph Self-Correction: Gửi SQL hỏng + Thông báo lỗi từ PostgreSQL vào LLM để tự khắc phục"""
    prompt = build_correction_prompt(
        question=question,
        failed_sql=failed_sql,
        error_msg=error_msg,
        schema_context=schema_context
    )
    cfg, lf_handler = _get_langfuse_config()

    # Bước 1: Thử với LLM chính
    try:
        llm = get_llm_model()
        if llm:
            chain = prompt | llm
            response = chain.invoke({}, config=cfg)
            _flush_langfuse(lf_handler)
            return clean_sql(response.content)
    except Exception as e:
        err_str = str(e)
        print(f"[LLM WARN] Self-correction primary model error -> Switching to failover...")
        try:
            fallback_llm = get_fallback_llm()
            if fallback_llm:
                chain = prompt | fallback_llm
                response = chain.invoke({}, config=cfg)
                _flush_langfuse(lf_handler)
                print("[LLM INFO] Self-correction failover model execution successful.")
                return clean_sql(response.content)
        except Exception as fe:
            print(f"[LLM ERROR] Self-correction failover model failed: {fe}")
    
    # Ẩn Hardcoded Fallback: Trả về câu lệnh hỏng ban đầu để hiển thị chính xác lỗi
    return failed_sql


def contextualize_question(question: str, chat_history: list = None) -> str:
    """Viết lại câu hỏi nối tiếp dựa trên lịch sử hội thoại thành câu hỏi tự thân (Standalone Question)"""
    if not chat_history:
        return question

    # Định dạng lịch sử tin nhắn ngắn gọn (lấy tối đa 5 lượt gần nhất)
    formatted_history = ""
    for msg in chat_history[-5:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = msg.get("content") or msg.get("question") or msg.get("sql", "")
        if content:
            formatted_history += f"- {role}: {content}\n"

    if not formatted_history.strip():
        return question

    from app.llm.prompts import get_contextualize_prompt
    prompt = get_contextualize_prompt(chat_history=formatted_history, question=question)
    cfg, lf_handler = _get_langfuse_config()

    try:
        llm = get_llm_model() or get_fallback_llm()
        if llm:
            chain = prompt | llm
            response = chain.invoke({"question": question}, config=cfg)
            _flush_langfuse(lf_handler)
            content = getattr(response, "content", str(response)).strip()
            # Làm sạch nếu AI lỡ bọc trong thẻ/quote
            content = re.sub(r'^["\']|["\']$', '', content).strip()
            if content and content != question:
                print(f"[STEP 1: QUERY REWRITER] Rewrote query -> '{content}'")
                return content
    except Exception as e:
        print(f"[STEP 1: QUERY REWRITER WARN] {e} -> Keeping original question.")

    return question
