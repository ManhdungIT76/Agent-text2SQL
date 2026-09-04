from langchain_core.prompts import ChatPromptTemplate
from app.database.schema import RETAIL_DATABASE_SCHEMA

SYSTEM_PROMPT = f"""- ROLE: Chuyên gia cơ sở dữ liệu PostgreSQL về mảng Bán lẻ.
- DATABASE SCHEMA:
{RETAIL_DATABASE_SCHEMA}
- LIMITS: Chỉ tạo câu lệnh SELECT để đọc dữ liệu. Nghiêm cấm DROP, DELETE, UPDATE, INSERT. Luôn giới hạn LIMIT tối đa 10 dòng.
- OUTPUT FORMAT: Chỉ trả về câu lệnh SQL hoàn chỉnh, không giải thích dông dài."""

def get_text2sql_prompt() -> ChatPromptTemplate:
    """Tạo ChatPromptTemplate dựa trên Prompt v1.0"""
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}")
    ])
