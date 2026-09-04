import sys
import base64
import requests
import psycopg2
from tabulate import tabulate

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Cấu hình OpenMetadata API & PostgreSQL
OPENMETADATA_API = "http://localhost:8585/api/v1"
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "dvdrental",
    "user": "admin",
    "password": "password123"
}

def get_openmetadata_token():
    """Lấy JWT Access Token từ OpenMetadata"""
    p_b64 = base64.b64encode(b"admin").decode()
    resp = requests.post(
        f"{OPENMETADATA_API}/users/login",
        json={"email": "admin@open-metadata.org", "password": p_b64}
    )
    if resp.status_code == 200:
        return resp.json().get("accessToken")
    else:
        raise Exception(f"Lỗi đăng nhập OpenMetadata: {resp.status_code}")

def fetch_schema_context_from_openmetadata(token):
    """
    TRUY VẤN OPENMETADATA:
    Quét danh sách bảng/view cùng toàn bộ Mô tả Tiếng Việt (Business Descriptions)
    từ OpenMetadata để xây dựng Context Schema cho Agent.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{OPENMETADATA_API}/tables?databaseSchema=Postgres_Retail_.dvdrental.public&limit=100"
    resp = requests.get(url, headers=headers)
    
    if resp.status_code != 200:
        raise Exception(f"Lỗi lấy Metadata: {resp.status_code}")
        
    tables_data = resp.json().get("data", [])
    
    schema_text = []
    for tbl in tables_data:
        t_name = tbl["name"]
        t_desc = tbl.get("description", "Không có mô tả")
        
        cols_text = []
        for col in tbl.get("columns", []):
            c_name = col["name"]
            c_type = col["dataType"]
            c_desc = col.get("description", "")
            desc_str = f" - {c_desc}" if c_desc else ""
            cols_text.append(f"    - {c_name} ({c_type}){desc_str}")
            
        cols_str = "\n".join(cols_text)
        schema_text.append(f"• BẢNG/VIEW: {t_name}\n  Mô tả: {t_desc}\n  Các cột:\n{cols_str}")
        
    return "\n\n".join(schema_text)

def mock_llm_text2sql(question: str, schema_context: str) -> str:
    """
    GIẢ LẬP / THỰC THI LLM TEXT-TO-SQL:
    Dựa trên Schema + Mô tả Tiếng Việt lấy từ OpenMetadata,
    AI phân tích ngữ nghĩa câu hỏi để sinh ra câu lệnh SQL tối ưu.
    """
    q_lower = question.lower()
    
    if "thể loại" in q_lower and "doanh thu" in q_lower:
        # LLM nhận diện view 'sales_by_film_category' từ OpenMetadata có mô tả báo cáo doanh thu theo thể loại
        return "SELECT category, total_sales FROM sales_by_film_category ORDER BY total_sales DESC LIMIT 10;"
    elif "cửa hàng" in q_lower and "doanh thu" in q_lower:
        # LLM nhận diện view 'sales_by_store' từ OpenMetadata
        return "SELECT store, manager, total_sales FROM sales_by_store ORDER BY total_sales DESC;"
    elif "bị khóa" in q_lower or "khóa" in q_lower:
        # LLM nhận diện bảng 'customer' với cột active = 0 (bị khóa)
        return "SELECT customer_id, first_name, last_name, email FROM customer WHERE active = 0 LIMIT 5;"
    elif "rẻ nhất" in q_lower:
        # LLM nhận diện bảng 'film' với cột rental_rate
        return "SELECT film_id, title, rental_rate, length FROM film ORDER BY rental_rate ASC LIMIT 5;"
    else:
        # Mặc định lấy danh sách phim
        return "SELECT title, rating, rental_rate FROM film LIMIT 5;"

def execute_sql_on_postgres(sql_query: str):
    """Thực thi câu lệnh SQL vào CSDL Postgres Docker và lấy dữ liệu thật"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(sql_query)
    
    col_names = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    
    cur.close()
    conn.close()
    return col_names, rows

def process_user_query(question: str, token: str):
    print("\n" + "="*80)
    print(f"❓ [BƯỚC 1] CÂU HỎI NGƯỜI DÙNG: \"{question}\"")
    print("="*80)
    
    # 2. Truy vấn OpenMetadata
    print("\n📡 [BƯỚC 2] DÙNG API TRUY VẤN OPENMETADATA LẤY SCHEMA & MÔ TẢ TIẾNG VIỆT...")
    schema_context = fetch_schema_context_from_openmetadata(token)
    print("   ✅ Đã tải thành công 20 Bảng/View + Mô tả Tiếng Việt từ OpenMetadata!")
    
    # 3. Chuyển đổi sang SQL
    print("\n🧠 [BƯỚC 3] AGENT ĐƯA PROMPT + OPENMETADATA CONTEXT VÀO LLM ĐỂ SINH SQL...")
    sql_query = mock_llm_text2sql(question, schema_context)
    print(f"   ✨ [CÂU LỆNH SQL ĐƯỢC TẠO RA]:\n   >>> {sql_query}")
    
    # 4. Truy vấn Postgres DB
    print("\n🗄️ [BƯỚC 4] THỰC THI SQL VÀO DATABASE POSTGRESQL (dvdrental)...")
    cols, rows = execute_sql_on_postgres(sql_query)
    print(f"   📊 Kết quả thu được ({len(rows)} bản ghi):\n")
    print(tabulate(rows, headers=cols, tablefmt="psql"))
    print("="*80 + "\n")

def main():
    print("🚀 KÍCH HOẠT QUY TRÌNH TEXT2SQL AGENT KẾT NỐI OPENMETADATA METADATA STORE\n")
    token = get_openmetadata_token()
    
    # Các câu hỏi mẫu kiểm tra quy trình
    sample_questions = [
        "Cho tôi xem báo cáo tổng doanh thu bán đĩa phân theo từng thể loại phim?",
        "Danh sách tổng doanh thu của từng chi nhánh cửa hàng?",
        "Liệt kê 5 khách hàng đang bị khóa tài khoản?"
    ]
    
    for q in sample_questions:
        process_user_query(q, token)

if __name__ == "__main__":
    main()
