import os
from dotenv import load_dotenv

# Tự động nạp file .env nếu có
load_dotenv()

class Config:
    """Quản lý các biến môi trường và cấu hình hệ thống"""
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5433"))
    DB_NAME: str = os.getenv("DB_NAME", "dvdrental")
    DB_USER: str = os.getenv("DB_USER", "admin")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password123")
    
    # Kết nối PostgreSQL DB URI
    DB_URI: str = os.getenv(
        "DB_URI", 
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    
    # Google Gemini API Key và Model
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

config = Config()
