"""
================================================================================
MODULE QUẢN TRỊ DỮ LIỆU TỰ ĐỘNG (AUTO DATA GOVERNANCE FOR OPENMETADATA)
================================================================================
Mục đích (Python 3.12 Standard):
1. Tự động đọc nhiều Database & Schemas trong CSDL thực tế, tự động khởi tạo 
   Service và Database tương ứng trên OpenMetadata Web API.
2. Kiểm tra các mối quan hệ (Foreign Keys) giữa các bảng:
   - Ghi log báo cáo các quan hệ FK hợp lệ đã tồn tại.
   - Phát hiện và xuất log báo cáo các quan hệ bị thiếu (Missing FK Candidates) 
     dựa trên phân tích tên cột (ví dụ: `xxx_id` liên kết với bảng `xxx`).
3. Tự động quét và bổ sung mô tả nghiệp vụ (Descriptions) tiếng Việt:
   - Trích xuất 1-2 dòng dữ liệu mẫu (Sample Data) từ CSDL thực tế để tăng 
     độ chính xác khi AI suy luận mô tả.
   - Đưa (Tên bảng, Tên cột, Dữ liệu mẫu) vào LLM để sinh mô tả tiếng Việt chuẩn.
   - Cập nhật mô tả trực tiếp lên OpenMetadata qua API PATCH.
================================================================================
"""

import sys
import json
import requests
from typing import Any
from sqlalchemy import create_engine, inspect, text

from app.config import config
from app.metadata.openmetadata_client import om_client
from app.llm.client import get_llm_model

# Đảm bảo mã hóa UTF-8 trên Windows Console (Python 3.12)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def auto_provision_database_and_services(engine: Any, service_name: str = "Postgres_Service") -> dict[str, Any]:
    """
    HÀM 1: TỰ ĐỘNG KHỞI TẠO SERVICE, DATABASE, SCHEMA VÀ UPLOAD TOÀN BỘ BẢNG CHÍNH + CỘT
    ----------------------------------------------------------------------------
    Chức năng:
    - Kiểm tra và tự động tạo mới DatabaseService (`Postgres_Service`) trên OpenMetadata.
    - Tạo Database (`dvdrental`) và DatabaseSchema (`public`).
    - Quét danh sách các BẢNG CHÍNH (bỏ qua Views) trong CSDL PostgreSQL và upload
      toàn bộ cấu trúc Bảng + Cột lên OpenMetadata API.
    """
    print(f"\n🚀 [BƯỚC 1]: Đang khởi tạo Service '{service_name}', Database '{config.DB_NAME}' & Upload toàn bộ Bảng/Cột...")
    
    # 1.1 Khởi tạo Service trên OpenMetadata
    service_info = om_client.get_or_create_database_service(
        service_name=service_name,
        db_type="Postgres",
        host_port=f"{config.DB_HOST}:{config.DB_PORT}"
    )
    
    # 1.2 Khởi tạo Database trên OpenMetadata
    db_info = om_client.get_or_create_database(
        service_name=service_name,
        db_name=config.DB_NAME
    )

    # 1.3 Khởi tạo Schema trên OpenMetadata
    schema_info = om_client.get_or_create_database_schema(
        service_name=service_name,
        db_name=config.DB_NAME,
        schema_name="public"
    )

    # 1.4 Quét CSDL PostgreSQL thực tế và upload toàn bộ Bảng chính + Cột
    inspector = inspect(engine)
    all_table_names = inspector.get_table_names(schema="public")
    view_names = set(inspector.get_view_names(schema="public"))
    base_tables = [t for t in all_table_names if t not in view_names]

    print(f"📦 Đang đẩy {len(base_tables)} Bảng chính từ PostgreSQL CSDL lên OpenMetadata API...")
    uploaded_tables = []
    for tbl in base_tables:
        cols_info = inspector.get_columns(tbl, schema="public")
        tbl_entity = om_client.create_table_entity(
            service_name=service_name,
            db_name=config.DB_NAME,
            schema_name="public",
            table_name=tbl,
            columns=cols_info
        )
        if tbl_entity:
            uploaded_tables.append(tbl)
    
    print(f"✅ [HOÀN TẤT BƯỚC 1]: Đã đẩy thành công {len(uploaded_tables)}/{len(base_tables)} Bảng chính kèm Cột lên OpenMetadata!")
    return {"service": service_info, "database": db_info, "schema": schema_info, "tables": uploaded_tables}


def check_and_log_relationships(engine: Any, schema_name: str = "public") -> dict[str, Any]:
    """
    HÀM 2: KIỂM TRA QUAN HỆ BẢNG & TỰ ĐỘNG BỔ SUNG CÁC RÀNG BUỘC FK BỊ THIẾU LÊN OPENMETADATA
    ----------------------------------------------------------------------------
    Chức năng:
    - Quét danh sách các BẢNG CHÍNH (Base Tables), bỏ qua các Bảng View.
    - Xuất log ✅ thành công cho các quan hệ FK chính thức.
    - Phân tích gợi ý ⚠️ các quan hệ bị thiếu (Missing FK candidates) và TỰ ĐỘNG PATCH
      ràng buộc Khóa ngoại mới này lên OpenMetadata API!
    """
    print(f"\n🔍 [BƯỚC 2]: Đang kiểm tra & tự động vá các ràng buộc Khóa ngoại (FK) bị thiếu lên OpenMetadata...")
    
    inspector = inspect(engine)
    all_table_names = inspector.get_table_names(schema=schema_name)
    view_names = set(inspector.get_view_names(schema=schema_name))
    
    base_tables = [t for t in all_table_names if t not in view_names]
    existing_fks: list[dict[str, Any]] = []
    missing_fk_candidates: list[dict[str, Any]] = []
    
    for idx, tbl in enumerate(base_tables, 1):
        print(f"\n   📋 [{idx}/{len(base_tables)}] Đang kiểm tra Bảng chính `{tbl}`:")
        fks = inspector.get_foreign_keys(tbl, schema=schema_name)
        cols = [c["name"] for c in inspector.get_columns(tbl, schema=schema_name)]
        
        if fks:
            for fk in fks:
                target_table = fk.get("referred_table")
                constrained_cols = fk.get("constrained_columns", [])
                referred_cols = fk.get("referred_columns", [])
                existing_fks.append({
                    "source_table": tbl,
                    "source_cols": constrained_cols,
                    "target_table": target_table,
                    "target_cols": referred_cols
                })
                print(f"      ✅ [FK FOUND]: `{tbl}`({', '.join(constrained_cols)}) ➔ `{target_table}`({', '.join(referred_cols)})")
        else:
            print(f"      ℹ️ Bảng `{tbl}` không chứa ràng buộc Khóa ngoại (FK) mặc định trong CSDL.")

        # 2.2 TỰ ĐỘNG VÁ KHÓA NGOẠI BỊ THIẾU
        for col in cols:
            if col.endswith("_id") and col != f"{tbl}_id" and col != "id":
                target_candidate = col[:-3] # Ví dụ: store_id -> store
                if target_candidate in base_tables:
                    is_already_fk = any(
                        fk["source_table"] == tbl and col in fk["source_cols"]
                        for fk in existing_fks
                    )
                    if not is_already_fk:
                        missing_fk_candidates.append({
                            "source_table": tbl,
                            "column": col,
                            "suggested_target_table": target_candidate
                        })
                        print(f"      ⚠️ [MISSING FK FOUND]: Cột `{col}` của Bảng `{tbl}` thiếu FK constraint nối với Bảng `{target_candidate}` trong CSDL!")
                        
                        # Gọi API OpenMetadata để lấy table_id và tự động patch FK
                        try:
                            headers = om_client.get_headers()
                            fqn = f"Postgres_Service.{config.DB_NAME}.{schema_name}.{tbl}"
                            tbl_res = requests.get(f"{om_client.api_url}/tables/name/{fqn}", headers=headers, timeout=5)
                            if tbl_res.status_code == 200:
                                tbl_id = tbl_res.json().get("id")
                                target_fqn = f"Postgres_Service.{config.DB_NAME}.{schema_name}.{target_candidate}.{col}"
                                om_client.add_foreign_key_constraint(tbl_id, col, target_fqn)
                        except Exception as patch_err:
                            print(f"      ⚠️ Lỗi tự động vá FK: {patch_err}")

    print(f"\n📊 [TỔNG KẾT BƯỚC 2]: Đã quét {len(base_tables)} Bảng chính. Tìm thấy {len(existing_fks)} FKs hợp lệ và đã tự động xử lý {len(missing_fk_candidates)} FKs bị thiếu!")
    return {"existing_fks": existing_fks, "missing_candidates": missing_fk_candidates}


def get_sample_data_for_table(engine: Any, table_name: str, schema_name: str = "public", limit: int = 2) -> list[dict[str, Any]]:
    """
    HÀM PHỤ TRỢ: Trích xuất 1-2 dòng dữ liệu mẫu (Sample Data) từ CSDL thực tế (Python 3.12)
    """
    try:
        with engine.connect() as conn:
            stmt = text(f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT {limit};')
            res = conn.execute(stmt)
            cols = list(res.keys())
            rows = res.fetchall()
            sample_records: list[dict[str, Any]] = []
            for row in rows:
                record: dict[str, Any] = {}
                for col_name, val in zip(cols, row):
                    str_val = str(val)
                    if len(str_val) > 50:
                        str_val = str_val[:47] + "..."
                    record[col_name] = str_val
                sample_records.append(record)
            return sample_records
    except Exception as e:
        print(f"      ⚠️ Không thể đọc sample data của bảng '{table_name}': {e}")
        return []


def generate_description_with_llm(table_name: str, columns_info: list[dict[str, Any]], sample_data: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Sử dụng LLM (Groq / Gemini / Qwen) để tự động phân tích tên Bảng, các Cột và Dữ liệu mẫu thực tế 
    để sinh Mô tả Tiếng Việt 100% linh hoạt và chuẩn nghiệp vụ cho bất kỳ Schema mới nào.
    """
    llm = get_llm_model()

    sample_str = json.dumps(sample_data, ensure_ascii=False, indent=2) if sample_data else "Không có dữ liệu mẫu"
    cols_str = ", ".join([f"{c['name']} ({c.get('dataType', 'text')})" for c in columns_info])

    # Fallback mặc định khi LLM chưa nạp được
    fallback_cols = {}
    for col in columns_info:
        c_name = col.get("name", "")
        fallback_cols[c_name] = f"Trường thông tin nghiệp vụ {c_name} của bảng {table_name}."
    default_fallback = {
        "table_description": f"Bảng quản lý dữ liệu nghiệp vụ {table_name}.",
        "column_descriptions": fallback_cols
    }

    if not llm:
        print(f"      ℹ️ LLM chưa sẵn sàng. Dùng mô tả mặc định cho bảng '{table_name}'.")
        return default_fallback

    prompt = f"""Bạn là Chuyên gia Quản trị Dữ liệu Doanh nghiệp (Enterprise Data Governance Specialist).
Nhiệm vụ của bạn là phân tích tên Bảng, danh sách Cột và Dữ liệu mẫu thực tế dưới đây để sinh mô tả TIẾNG VIỆT 100% chuẩn nghiệp vụ cho bảng và từng cột.

[THÔNG TIN BẢNG CSDL]:
- Tên bảng: {table_name}
- Danh sách cột: {cols_str}

[DỮ LIỆU MẪU THỰC TẾ (1-2 DÒNG)]:
{sample_str}

[YÊU CẦU BẮT BUỘC]:
1. Mô tả phải viết bằng **TIẾNG VIỆT CHUẨN**, chuyên nghiệp, giàu ý nghĩa nghiệp vụ, giúp AI Text2SQL dễ hiểu.
2. Trả về DUY NHẤT một chuỗi JSON thuần đúng cấu trúc sau (KHÔNG kèm markdown ```json hay lời giải thích):
{{
  "table_description": "Mô tả tiếng Việt chuyên nghiệp tổng quan về mục đích nghiệp vụ của bảng",
  "column_descriptions": {{
    "ten_cot_1": "Mô tả tiếng Việt chi tiết nghĩa nghiệp vụ của cột 1",
    "ten_cot_2": "Mô tả tiếng Việt chi tiết nghĩa nghiệp vụ của cột 2"
  }}
}}
"""
    try:
        res = llm.invoke(prompt)
        text_resp = str(res.content).strip()
        if text_resp.startswith("```"):
            text_resp = text_resp.split("```")[1]
            if text_resp.startswith("json"):
                text_resp = text_resp[4:]
        text_resp = text_resp.strip()
        parsed: dict[str, Any] = json.loads(text_resp)
        if "table_description" in parsed and "column_descriptions" in parsed:
            return parsed
        return default_fallback
    except Exception as e:
        print(f"      ⚠️ Lỗi khi gọi LLM sinh mô tả cho bảng '{table_name}' ({e}). Sử dụng mô tả dự phòng.")
        return default_fallback


def auto_generate_and_patch_descriptions(engine: Any, service_name: str = "Postgres_Service", force_update: bool = True) -> int:
    """
    HÀM 3: TỰ ĐỘNG SINH & ĐÈ MÔ TẢ TIẾNG VIỆT PHONG PHÚ CHO TẤT CẢ BẢNG VÀ CỘT LÊN OPENMETADATA
    ----------------------------------------------------------------------------
    Chức năng:
    - Quét các BẢNG CHÍNH (loại bỏ Views) trên OpenMetadata.
    - Lấy 1-2 dòng dữ liệu mẫu từ CSDL PostgreSQL.
    - Sinh mô tả tiếng Việt chuyên nghiệp.
    - Gửi PATCH (đè) trực tiếp lên OpenMetadata API.
    """
    print("\n📝 [BƯỚC 3]: Đang cập nhật Mô tả tiếng Việt chuyên nghiệp cho BẢNG & CỘT lên OpenMetadata...")
    
    inspector = inspect(engine)
    view_names = set(inspector.get_view_names(schema="public"))

    token = om_client.get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    url = f"{om_client.api_url}/tables?fields=columns&limit=100"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ Lỗi đọc danh sách bảng từ OpenMetadata: {resp.status_code}")
        return 0

    tables: list[dict[str, Any]] = resp.json().get("data", [])
    success_count = 0
    skipped_views = 0

    print(f"📋 Tổng số bảng trên OpenMetadata: {len(tables)}. Bắt đầu cập nhật từng bảng:\n")

    for idx, tbl in enumerate(tables, 1):
        tbl_id = tbl.get("id")
        tbl_name = tbl.get("name")
        tbl_type = tbl.get("tableType", "")
        cols: list[dict[str, Any]] = tbl.get("columns", [])
        
        # LỌC BỎ VIEWS
        if tbl_name in view_names or tbl_type == "View" or "list" in tbl_name or "sales_by" in tbl_name:
            skipped_views += 1
            print(f"   ⏩ [{idx}/{len(tables)}] [SKIP VIEW]: Bảng '{tbl_name}' là View ➔ Bỏ qua không xử lý.")
            continue

        print(f"   ⚙️ [{idx}/{len(tables)}] [UPDATING TABLE]: Đang nạp mô tả tiếng Việt chuẩn cho Bảng chính '{tbl_name}' ({len(cols)} cột)...")
        
        # 3.1 Trích xuất 1-2 dòng dữ liệu mẫu
        sample_data = get_sample_data_for_table(engine, tbl_name, limit=2)
        
        # 3.2 Đưa vào Tri thức nghiệp vụ tiếng Việt / LLM suy luận
        llm_output = generate_description_with_llm(tbl_name, cols, sample_data)
        
        table_desc = llm_output.get("table_description", f"Bảng dữ liệu nghiệp vụ {tbl_name}")
        col_descs = llm_output.get("column_descriptions", {})

        # 3.3 Tạo danh sách thao tác JSON Patch (Đè toàn bộ mô tả bảng và từng cột)
        patch_ops: list[dict[str, Any]] = [
            {
                "op": "add",
                "path": "/description",
                "value": table_desc
            }
        ]

        for c_idx, col in enumerate(cols):
            c_name = col.get("name")
            c_desc = col_descs.get(c_name, f"Trường thông tin nghiệp vụ {c_name} của bảng {tbl_name}.")
            patch_ops.append({
                "op": "add",
                "path": f"/columns/{c_idx}/description",
                "value": c_desc
            })

        # 3.4 Patch lên OpenMetadata API
        if patch_ops and tbl_id:
            patched_ok = om_client.patch_table_or_column_description(tbl_id, patch_ops)
            if patched_ok:
                success_count += 1
                print(f"      ✅ [PATCH SUCCESS]: Đã cập nhật thành công mô tả bảng + {len(patch_ops)-1} cột cho '{tbl_name}'!")
            else:
                print(f"      ⚠️ [PATCH ERROR]: Không thể patch mô tả cho bảng '{tbl_name}'")

    print(f"\n🎉 HOÀN TẤT BƯỚC 3: Cập nhật thành công mô tả tiếng Việt cho {success_count} Bảng chính!")
    return success_count


def run_full_governance_pipeline() -> None:
    """
    HÀM THỰC THI TOÀN BỘ QUY TRÌNH DATA GOVERNANCE TỰ ĐỘNG (Python 3.12 Standard)
    """
    print("=================================================================================")
    print("🚀 BẮT ĐẦU QUY TRÌNH AUTOMATED DATA GOVERNANCE FOR TEXT2SQL (PYTHON 3.12)")
    print("=================================================================================")

    # Khởi tạo SQLAlchemy Engine kết nối CSDL PostgreSQL
    engine = create_engine(config.DB_URI)
    
    # Bước 1: Khởi tạo Service, Database, Schema và Upload toàn bộ Bảng chính + Cột
    auto_provision_database_and_services(engine)
    
    # Bước 2: Kiểm tra Relationship & xuất Log
    check_and_log_relationships(engine)
    
    # Bước 3: Tự động sinh & Cập nhật mô tả tiếng Việt từ Sample Data + LLM
    auto_generate_and_patch_descriptions(engine)
    
    # Cập nhật lại Local Disk Cache của OpenMetadataClient
    om_client.sync_cache_from_openmetadata()
    
    print("\n=================================================================================")
    print("✨ QUY TRÌNH DATA GOVERNANCE HOÀN TẤT THÀNH CÔNG! HỆ THỐNG ĐÃ SẴN SÀNG CHO MCP SERVER.")
    print("=================================================================================")


if __name__ == "__main__":
    run_full_governance_pipeline()
