from langchain_community.utilities import SQLDatabase

def execute_sql(db: SQLDatabase, sql_query: str) -> str:
    """Thực thi câu lệnh SQL trên PostgreSQL Docker và trả về kết quả"""
    try:
        return db.run(sql_query)
    except Exception as e:
        return f"Lỗi thực thi SQL: {e}"
