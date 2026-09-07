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
    
    # Provider LLM được chọn (groq hoặc gemini)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").lower()
    
    # Groq API Key và Model
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "groq/compound")

    # Google Gemini API Key và Model
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # Langfuse Observability & Prompt Governance
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip('"')
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "").strip('"')
    LANGFUSE_HOST: str = (
        os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"
    ).strip('"')

config = Config()
