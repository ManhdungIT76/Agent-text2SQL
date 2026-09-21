import os
import json
import time
import base64
import requests
from typing import Optional, Dict, Any

CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), "schema_cache.json")
CACHE_TTL_SECONDS = 86400  # 24 giờ (86,400 giây)


def extract_dynamic_foreign_keys_from_db() -> Dict[str, list]:
    """
    Rút trích động 100% Khóa Ngoại trực tiếp từ CSDL PostgreSQL (SQLAlchemy Inspect + Dynamic Pattern Inference).
    KHÔNG sử dụng bất kỳ từ điển hardcode nào!
    """
    try:
        from sqlalchemy import create_engine, inspect
        from app.config import config
        engine = create_engine(config.DB_URI)
        inspector = inspect(engine)
        all_tables = inspector.get_table_names(schema="public")
        views = set(inspector.get_view_names(schema="public"))
        base_tables = [t for t in all_tables if t not in views]

        dynamic_fks = {}
        for tbl in base_tables:
            tbl_fks = []
            # 1. Quét FKs chính thức trong PostgreSQL DDL
            existing_fks = inspector.get_foreign_keys(tbl, schema="public")
            for fk in existing_fks:
                target_tbl = fk.get("referred_table")
                src_cols = fk.get("constrained_columns", [])
                ref_cols = fk.get("referred_columns", [])
                if target_tbl and src_cols:
                    tbl_fks.append({
                        "columns": src_cols,
                        "target_table": target_tbl,
                        "target_column": ref_cols[0] if ref_cols else src_cols[0]
                    })

            # 2. Tự động phát hiện các FKs dựa trên phân tích tên cột (*_id -> target table)
            cols = inspector.get_columns(tbl, schema="public")
            for c in cols:
                col_name = c["name"]
                if col_name.endswith("_id") and col_name != f"{tbl}_id" and col_name != "id":
                    target_candidate = col_name[:-3]
                    # Nếu tên cột có prefix (ví dụ manager_staff_id), thử tìm tên bảng tương ứng (staff)
                    if target_candidate not in base_tables and "_" in target_candidate:
                        possible_table = target_candidate.split("_")[-1]
                        if possible_table in base_tables:
                            target_candidate = possible_table

                    if target_candidate in base_tables:
                        already_has = any(fk["target_table"] == target_candidate and col_name in fk["columns"] for fk in tbl_fks)
                        if not already_has:
                            target_pk = f"{target_candidate}_id"
                            tbl_fks.append({
                                "columns": [col_name],
                                "target_table": target_candidate,
                                "target_column": target_pk
                            })

            dynamic_fks[tbl] = tbl_fks
        return dynamic_fks
    except Exception as e:
        print(f"⚠️ [DYNAMIC FK EXTRACTION ERROR]: ({e})")
        return {}


class OpenMetadataClient:
    """Client kết nối OpenMetadata REST API & Quản lý Local Disk Cache (Tự động Sync hàng ngày)"""
    
    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.getenv("OPENMETADATA_API", "http://localhost:8585/api/v1")
        self.token: Optional[str] = None

    def check_connection(self) -> bool:
        """Kiểm tra xem OpenMetadata REST API Server có đang Online không"""
        try:
            resp = requests.get(f"{self.api_url}/system/version", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_token(self) -> str:
        """Lấy JWT Access Token từ OpenMetadata Server"""
        if self.token:
            return self.token
            
        p_b64 = base64.b64encode(b"admin").decode()
        resp = requests.post(
            f"{self.api_url}/users/login",
            json={"email": "admin@open-metadata.org", "password": p_b64},
            timeout=10
        )
        if resp.status_code == 200:
            self.token = resp.json().get("accessToken")
            return self.token
        else:
            raise Exception(f"Lỗi đăng nhập OpenMetadata API: Status {resp.status_code} - {resp.text}")

    def sync_cache_from_openmetadata(self) -> Dict[str, Any]:
        """
        Đồng bộ Metadata từ OpenMetadata API và lưu trữ cấu trúc dạng JSON vào file schema_cache.json
        """
        from app.config import config
        print("🔄 [OPENMETADATA AUTO-SYNC]: Đang tự động cập nhật Metadata từ OpenMetadata...")
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        db_schema_fqn = f"{config.OM_SERVICE_NAME}.{config.OM_DATABASE}.{config.OM_SCHEMA}"
        url = f"{self.api_url}/tables?databaseSchema={db_schema_fqn}&fields=columns,tableConstraints&limit=100"

        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"Lỗi lấy Metadata từ OpenMetadata: Status {resp.status_code} - {resp.text}")
            
        tables_data = resp.json().get("data", [])
        
        # Rút trích Khóa Ngoại ĐỘNG 100% từ CSDL PostgreSQL (Không Hardcode)
        db_fks_map = extract_dynamic_foreign_keys_from_db()

        cache_data = {
            "last_synced_timestamp": time.time(),
            "total_tables": len(tables_data),
            "tables": {}
        }
        
        for tbl in tables_data:
            t_name = tbl.get("name", "")
            t_desc = tbl.get("description", "Không có mô tả")
            
            cols = []
            for col in tbl.get("columns", []):
                cols.append({
                    "name": col.get("name", ""),
                    "type": col.get("dataType", ""),
                    "description": col.get("description", "")
                })
                
            fks = []
            for c in tbl.get("tableConstraints", []):
                if c.get("constraintType") == "FOREIGN_KEY":
                    ref_cols = c.get("referredColumns", [])
                    target_info = ref_cols[0] if ref_cols else ""
                    parts = target_info.split(".")
                    target_table = parts[-2] if len(parts) >= 2 else target_info
                    target_col = parts[-1] if len(parts) >= 1 else ""
                    fks.append({
                        "columns": c.get("columns", []),
                        "target_table": target_table,
                        "target_column": target_col
                    })

            # Nếu OpenMetadata chưa trả về Khóa ngoại (FKs), sử dụng Khóa Ngoại ĐỘNG quét từ CSDL PostgreSQL
            if not fks and t_name in db_fks_map:
                fks = db_fks_map[t_name]

            cache_data["tables"][t_name] = {
                "name": t_name,
                "description": t_desc,
                "columns": cols,
                "foreign_keys": fks
            }
            
        # Ghi ra file schema_cache.json
        with open(CACHE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
        print(f"💾 [CACHE AUTO-UPDATED]: Đã lưu bộ nhớ đệm {len(tables_data)} bảng vào {CACHE_FILE_PATH}")
        return cache_data

    def load_local_cache(self) -> Dict[str, Any]:
        """
        Ưu tiên hàng đầu: Luôn thử gọi trực tiếp OpenMetadata REST API Live để đồng bộ mô tả mới nhất.
        Nếu OpenMetadata Server bị tắt hoặc mất mạng -> Tự động Fallback đọc file đĩa cục bộ (schema_cache.json).
        """
        # Bước 1: Ưu tiên thử gọi trực tiếp OpenMetadata Server Live
        try:
            return self.sync_cache_from_openmetadata()
        except Exception as sync_err:
            print(f"⚠️ [OPENMETADATA OFFLINE / TIMEOUT]: Không kết nối được OpenMetadata Server ({sync_err}). Chuyển sang Fallback đọc Local Disk Cache...")

        # Bước 2: Fallback đọc từ file schema_cache.json nếu OpenMetadata Server bị lỗi
        if os.path.exists(CACHE_FILE_PATH):
            try:
                with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    print(f"💾 [DISK CACHE FALLBACK]: Đã nạp thành công Metadata từ file đĩa cục bộ {CACHE_FILE_PATH}")
                    return data
            except Exception as read_err:
                print(f"❌ [LỖI ĐỌC DISK CACHE]: ({read_err})")

        return {"tables": {}}


    def fetch_schema_context(self) -> str:
        """
        Trả về chuỗi Schema Context Tiếng Việt từ Disk Cache.
        """
        data = self.load_local_cache()
        tables = data.get("tables", {})
        schema_lines = []
        for t_name, tbl in tables.items():
            t_desc = tbl.get("description", "")
            cols_desc = [f"{c.get('name')} ({c.get('type')})" for c in tbl.get("columns", [])]
            cols_str = ", ".join(cols_desc)
            desc_str = f" ({t_desc})" if t_desc else ""
            schema_lines.append(f"• BẢNG `{t_name}`{desc_str}:\n  Các cột: {cols_str}")
        return "\n\n".join(schema_lines)

    def get_schema_overview(self) -> str:
        """
        Trả về chuỗi tổng quan (Overview) tên bảng và mô tả nghiệp vụ cho LLM ở Giai đoạn 2 (Prompt 1).
        """
        data = self.load_local_cache()
        tables = data.get("tables", {})
        overview_lines = []
        for t_name, tbl in tables.items():
            t_desc = tbl.get("description", "Bảng dữ liệu trong CSDL.")
            overview_lines.append(f"• BẢNG `{t_name}`: {t_desc}")
        return "\n".join(overview_lines)

# Instance singleton
om_client = OpenMetadataClient()