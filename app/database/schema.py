# Định nghĩa cấu trúc các bảng PostgreSQL rút trích động từ OpenMetadata Local Cache + Smart Retriever
from app.metadata.openmetadata_client import om_client
from app.metadata.schema_retriever import schema_retriever

FALLBACK_DATABASE_SCHEMA = """  + Bảng customer: customer_id (int), first_name (varchar), last_name (varchar), email (varchar), active (int: 1-hoạt động, 0-khóa).
  + Bảng film: film_id (int), title (varchar), release_year (int), rental_rate (numeric), length (int).
  + Bảng payment: payment_id (int), customer_id (int), amount (numeric), payment_date (timestamp)."""

def get_dynamic_schema_context(question: str = None) -> str:
    """
    Lấy Schema context đã được tối ưu hóa (Chỉ lấy 1-2 bảng liên quan nhất giúp tiết kiệm 95% Token)
    Đồng thời đọc từ Local Disk Cache (0ms latency).
    """
    if question:
        try:
            return schema_retriever.get_relevant_schema_context(question, top_k=2)
        except Exception as e:
            print(f"[CẢNH BÁO RETRIEVER]: ({e}), fallback về lấy từ OpenMetadata Client...")

    try:
        schema = om_client.fetch_schema_context()
        if schema:
            return schema
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể kết nối OpenMetadata API ({e}), dùng schema dự phòng.")
    return FALLBACK_DATABASE_SCHEMA
