from langchain_community.utilities import SQLDatabase
from sqlalchemy import text


def execute_sql(db: SQLDatabase, sql_query: str):
    """Thực thi câu lệnh SQL trên PostgreSQL Docker và trả về danh sách bản ghi kèm tên cột"""
    clean_query = sql_query.strip()
    try:
        # Nếu là câu lệnh SELECT hoặc WITH (CTE), trả về danh sách dicts có tên cột chuẩn xác
        if clean_query.upper().startswith("SELECT") or clean_query.upper().startswith("WITH"):
            with db._engine.connect() as conn:
                res = conn.execute(text(clean_query))
                cols = list(res.keys())
                rows = res.fetchall()
                return [dict(zip(cols, row)) for row in rows]
        
        # Với các thao tác khác (hoặc view), dùng db.run
        raw_res = db.run(clean_query)
        if isinstance(raw_res, str) and raw_res.startswith("[("):
            import ast
            try:
                parsed_tuples = ast.literal_eval(raw_res)
                return parsed_tuples
            except Exception:
                pass
        return raw_res
    except Exception as e:
        raise e
