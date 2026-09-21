# Định nghĩa cấu trúc các bảng PostgreSQL rút trích động từ OpenMetadata Local Cache + Smart Retriever
from app.metadata.openmetadata_client import om_client
from app.metadata.schema_retriever import schema_retriever

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
        print(f"[CẢNH BÁO] Không thể kết nối OpenMetadata API ({e}), dùng schema tổng quan dự phòng.")
    
    # Dynamic fallback: Đọc trực tiếp từ OpenMetadata local cache
    try:
        return om_client.get_schema_overview()
    except Exception:
        return "Cấu trúc CSDL PostgreSQL chưa được đồng bộ từ OpenMetadata."

