from langchain_community.utilities import SQLDatabase
from app.config import config

def get_db_connection() -> SQLDatabase:
    """Khởi tạo và trả về kết nối SQLDatabase từ LangChain"""
    return SQLDatabase.from_uri(config.DB_URI)
