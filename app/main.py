import sys

# Đảm bảo UTF-8 cho stdout trên Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.database.connection import get_db_connection
from app.database.executor import execute_sql
from app.llm.client import generate_sql

def run_query(db, question: str):
    print("=" * 70)
    print(f"Câu hỏi: {question}")
    
    # 1. Gửi câu hỏi lên AI Cloud (LangChain + Gemini)
    sql_query = generate_sql(question)
    print(f"\n[SQL được AI tạo ra]:\n{sql_query}\n")
    
    # 2. Thực thi câu lệnh SQL vào Docker Postgres (dvdrental)
    results = execute_sql(db, sql_query)
    print(f"[Kết quả từ Docker Postgres]:\n{results}")
    print("=" * 70 + "\n")

def main():
    db = get_db_connection()
    questions = [
        "Cho tôi danh sách các khách hàng có tài khoản đang bị khóa?",
        "Liệt kê 5 bộ phim có giá thuê đĩa rẻ nhất?",
        "Hệ thống đã thu về tổng cộng bao nhiêu doanh thu tiền mặt?"
    ]
    
    for q in questions:
        run_query(db, q)

if __name__ == "__main__":
    main()
