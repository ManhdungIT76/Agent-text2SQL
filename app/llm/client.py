from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import config
from app.llm.prompts import get_text2sql_prompt

def clean_sql(raw_output: str) -> str:
    """Trích xuất câu lệnh SQL sạch từ output của AI (loại bỏ markdown block nếu có)"""
    sql = raw_output.strip()
    if sql.startswith("```sql"):
        sql = sql[6:]
    elif sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
    return sql.strip()

def generate_sql(question: str) -> str:
    """Gửi câu hỏi lên Gemini AI Cloud qua LangChain để tạo câu lệnh SQL"""
    if config.GOOGLE_API_KEY:
        llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL, 
            google_api_key=config.GOOGLE_API_KEY, 
            temperature=0
        )
        prompt = get_text2sql_prompt()
        chain = prompt | llm
        response = chain.invoke({"question": question})
        return clean_sql(response.content)
    # else:
    #     # Nếu chưa cài đặt GOOGLE_API_KEY trong hệ thống, thực thi qua mô phỏng Prompt v1.0 tuân thủ chính xác schema
    #     q_lower = question.lower()
    #     if "bị khóa" in q_lower or "khóa" in q_lower:
    #         return "SELECT customer_id, first_name, last_name, email, active FROM customer WHERE active = 0 LIMIT 10;"
    #     elif "rẻ nhất" in q_lower:
    #         return "SELECT film_id, title, release_year, rental_rate, length FROM film ORDER BY rental_rate ASC LIMIT 5;"
    #     elif "doanh thu" in q_lower:
    #         return "SELECT SUM(amount) AS total_revenue FROM payment;"
    #     else:
    #         return "SELECT * FROM customer LIMIT 10;"

