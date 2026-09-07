import os
import json
import time
import base64
import requests
from typing import Optional, Dict, Any

CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), "schema_cache.json")
CACHE_TTL_SECONDS = 86400  # 24 giờ (86,400 giây)

class OpenMetadataClient:
    """Client kết nối OpenMetadata REST API & Quản lý Local Disk Cache (Tự động Sync hàng ngày)"""
    
    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.getenv("OPENMETADATA_API", "http://localhost:8585/api/v1")
        self.token: Optional[str] = None

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
        print("🔄 [OPENMETADATA AUTO-SYNC]: Đang tự động cập nhật Metadata 20 Bảng/Views từ OpenMetadata...")
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.api_url}/tables?databaseSchema=Postgres_Retail_.dvdrental.public&fields=columns,tableConstraints&limit=100"
        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"Lỗi lấy Metadata từ OpenMetadata: Status {resp.status_code} - {resp.text}")
            
        tables_data = resp.json().get("data", [])
        
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
        Đọc nhanh cấu trúc Schema từ Local Disk Cache.
        Tự động làm mới (Auto-Sync) nếu file cache đã cũ hơn 24 giờ.
        """
        if not os.path.exists(CACHE_FILE_PATH):
            return self.sync_cache_from_openmetadata()
            
        try:
            with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            last_synced = data.get("last_synced_timestamp", 0)
            current_time = time.time()
            
            # Nếu file cache đã cũ hơn 24 giờ (86400 giây), tự động đồng bộ làm mới ngầm
            if (current_time - last_synced) > CACHE_TTL_SECONDS:
                print("⏰ [CACHE EXPIRED > 24H]: File cache đã quá 24 tiếng, đang tự động đồng bộ lại từ OpenMetadata...")
                return self.sync_cache_from_openmetadata()
                
            return data
        except Exception as e:
            print(f"[CẢNH BÁO CACHE]: Không thể đọc cache file ({e}), tự động đồng bộ lại...")
            return self.sync_cache_from_openmetadata()

# Instance singleton
om_client = OpenMetadataClient()
