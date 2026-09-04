import sys
import base64
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

OPENMETADATA_API = "http://localhost:8585/api/v1"
p_b64 = base64.b64encode(b"admin").decode()

login_resp = requests.post(
    f"{OPENMETADATA_API}/users/login",
    json={"email": "admin@open-metadata.org", "password": p_b64}
)
if login_resp.status_code != 200:
    print(f"❌ Lỗi đăng nhập OpenMetadata API: {login_resp.status_code}")
    sys.exit(1)

token = login_resp.json().get("accessToken")
headers = {"Authorization": f"Bearer {token}"}
patch_headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json-patch+json"
}

# Lấy danh sách bảng từ OpenMetadata
tables_resp = requests.get(
    f"{OPENMETADATA_API}/tables?databaseSchema=Postgres_Retail_.dvdrental.public&limit=100",
    headers=headers
)
tables = tables_resp.json().get("data", [])
table_dict = {t["name"]: t for t in tables}

# Từ điển mô tả chuẩn nghiệp vụ Bán lẻ & Thuê đĩa bằng tiếng Việt
METADATA_DESCRIPTIONS = {
    "customer": {
        "description": "Bảng quản lý thông tin tài khoản khách hàng mua/thuê đĩa.",
        "columns": {
            "customer_id": "Mã định danh duy nhất của khách hàng (Primary Key).",
            "store_id": "Mã cửa hàng mà khách hàng đăng ký thành viên.",
            "first_name": "Tên của khách hàng.",
            "last_name": "Họ và tên đệm của khách hàng.",
            "email": "Địa chỉ Email liên hệ của khách hàng.",
            "address_id": "Mã địa chỉ liên kết với bảng address.",
            "activebool": "Cờ trạng thái tài khoản boolean (True: Hoạt động, False: Khóa).",
            "create_date": "Ngày tài khoản khách hàng được tạo trong hệ thống.",
            "last_update": "Thời gian cập nhật thông tin khách hàng lần gần nhất.",
            "active": "Trạng thái tài khoản (1: Đang hoạt động, 0: Tài khoản bị khóa)."
        }
    },
    "film": {
        "description": "Bảng danh mục các bộ phim sẵn có trong hệ thống cửa hàng bán lẻ.",
        "columns": {
            "film_id": "Mã định danh duy nhất của bộ phim (Primary Key).",
            "title": "Tên tiêu đề bộ phim.",
            "description": "Tóm tắt nội dung kịch bản phim.",
            "release_year": "Năm bộ phim được phát hành/khởi chiếu.",
            "language_id": "Mã ngôn ngữ gốc của phim (khóa ngoại nối với bảng language).",
            "rental_duration": "Số ngày tối đa khách hàng được phép thuê đĩa phim.",
            "rental_rate": "Giá tiền thuê đĩa phim đơn vị USD.",
            "length": "Thời lượng phát sóng của bộ phim (tính theo phút).",
            "replacement_cost": "Chi phí đền bù khi khách làm mất đĩa phim (USD).",
            "rating": "Phân loại độ tuổi xem phim (G, PG, PG-13, R, NC-17).",
            "last_update": "Thời gian cập nhật thông tin phim gần nhất.",
            "special_features": "Các tính năng đặc biệt (Trailers, Commentaries, Deleted Scenes).",
            "fulltext": "Dữ liệu chỉ mục tìm kiếm văn bản toàn diện của phim."
        }
    },
    "payment": {
        "description": "Bảng ghi nhận tất cả các giao dịch thanh toán tiền mặt từ khách hàng.",
        "columns": {
            "payment_id": "Mã định danh duy nhất của giao dịch thanh toán (Primary Key).",
            "customer_id": "Mã khách hàng thực hiện thanh toán (khóa ngoại nối customer).",
            "staff_id": "Mã nhân viên thu ngân xử lý thanh toán (khóa ngoại nối staff).",
            "rental_id": "Mã đơn thuê đĩa liên quan (khóa ngoại nối rental).",
            "amount": "Tổng số tiền thanh toán thực tế của giao dịch (USD).",
            "payment_date": "Thời gian giao dịch thanh toán được hoàn tất."
        }
    },
    "rental": {
        "description": "Bảng quản lý danh sách các đơn thuê đĩa đĩa phim của khách hàng.",
        "columns": {
            "rental_id": "Mã định danh đơn thuê đĩa (Primary Key).",
            "rental_date": "Thời gian khách hàng bắt đầu thuê đĩa.",
            "inventory_id": "Mã bản sao đĩa phim trong kho (khóa ngoại nối inventory).",
            "customer_id": "Mã khách hàng thuê đĩa (khóa ngoại nối customer).",
            "return_date": "Thời gian khách hàng mang đĩa trả lại cửa hàng.",
            "staff_id": "Mã nhân viên xử lý cho thuê đĩa (khóa ngoại nối staff).",
            "last_update": "Thời gian cập nhật thông tin đơn thuê gần nhất."
        }
    },
    "inventory": {
        "description": "Bảng lưu trữ thông tin tồn kho bản sao các đĩa phim tại từng cửa hàng.",
        "columns": {
            "inventory_id": "Mã bản sao đĩa phim trong kho (Primary Key).",
            "film_id": "Mã bộ phim (khóa ngoại nối với bảng film).",
            "store_id": "Mã cửa hàng lưu trữ đĩa (khóa ngoại nối với bảng store).",
            "last_update": "Thời gian cập nhật tồn kho đĩa gần nhất."
        }
    },
    "staff": {
        "description": "Bảng quản lý danh sách nhân viên phục vụ tại các cửa hàng.",
        "columns": {
            "staff_id": "Mã định danh duy nhất của nhân viên (Primary Key).",
            "first_name": "Tên nhân viên.",
            "last_name": "Họ nhân viên.",
            "address_id": "Mã địa chỉ của nhân viên.",
            "email": "Email công việc của nhân viên.",
            "store_id": "Mã cửa hàng nhân viên đang làm việc.",
            "active": "Trạng thái làm việc (True: Đang làm việc, False: Đã nghỉ việc).",
            "username": "Tên tài khoản đăng nhập hệ thống của nhân viên.",
            "password": "Mật khẩu mã hóa của nhân viên.",
            "last_update": "Thời gian cập nhật thông tin nhân viên gần nhất.",
            "picture": "Ảnh đại diện của nhân viên."
        }
    },
    "store": {
        "description": "Bảng quản lý danh sách các chi nhánh cửa hàng bán lẻ/cho thuê đĩa.",
        "columns": {
            "store_id": "Mã định danh duy nhất của cửa hàng (Primary Key).",
            "manager_staff_id": "Mã nhân viên quản lý cửa hàng (nối với bảng staff).",
            "address_id": "Mã địa chỉ trụ sở cửa hàng (nối với bảng address).",
            "last_update": "Thời gian cập nhật thông tin cửa hàng gần nhất."
        }
    },
    "actor": {
        "description": "Bảng danh mục các diễn viên tham gia đóng phim.",
        "columns": {
            "actor_id": "Mã định danh duy nhất của diễn viên (Primary Key).",
            "first_name": "Tên diễn viên.",
            "last_name": "Họ diễn viên.",
            "last_update": "Thời gian cập nhật thông tin diễn viên gần nhất."
        }
    },
    "category": {
        "description": "Bảng danh mục các thể loại phim (Hành động, Hài hước, Tình cảm,...).",
        "columns": {
            "category_id": "Mã định danh thể loại phim (Primary Key).",
            "name": "Tên thể loại phim (Action, Comedy, Drama, Sci-Fi,...).",
            "last_update": "Thời gian cập nhật thể loại gần nhất."
        }
    },
    "address": {
        "description": "Bảng thông tin địa chỉ liên hệ của khách hàng, nhân viên và cửa hàng.",
        "columns": {
            "address_id": "Mã định danh địa chỉ (Primary Key).",
            "address": "Tên đường/Số nhà chi tiết.",
            "address2": "Địa chỉ bổ sung (phòng, tầng,...).",
            "district": "Quận/Huyện hoặc Bang.",
            "city_id": "Mã thành phố (khóa ngoại nối với bảng city).",
            "postal_code": "Mã bưu chính.",
            "phone": "Số điện thoại liên hệ.",
            "last_update": "Thời gian cập nhật địa chỉ gần nhất."
        }
    },
    "city": {
        "description": "Bảng danh mục các thành phố.",
        "columns": {
            "city_id": "Mã định danh thành phố (Primary Key).",
            "city": "Tên thành phố.",
            "country_id": "Mã quốc gia (khóa ngoại nối với bảng country).",
            "last_update": "Thời gian cập nhật gần nhất."
        }
    },
    "country": {
        "description": "Bảng danh mục các quốc gia.",
        "columns": {
            "country_id": "Mã định danh quốc gia (Primary Key).",
            "country": "Tên quốc gia.",
            "last_update": "Thời gian cập nhật gần nhất."
        }
    },
    "language": {
        "description": "Bảng danh mục ngôn ngữ phát thanh của phim.",
        "columns": {
            "language_id": "Mã định danh ngôn ngữ (Primary Key).",
            "name": "Tên ngôn ngữ (English, Italian, Japanese, Mandarin,...).",
            "last_update": "Thời gian cập nhật gần nhất."
        }
    },
    "film_actor": {
        "description": "Bảng liên kết nhiều-nhiều giữa Phim (film) và Diễn viên (actor).",
        "columns": {
            "actor_id": "Mã diễn viên (khóa ngoại nối bảng actor).",
            "film_id": "Mã bộ phim (khóa ngoại nối bảng film).",
            "last_update": "Thời gian cập nhật gần nhất."
        }
    },
    "film_category": {
        "description": "Bảng liên kết nhiều-nhiều giữa Phim (film) và Thể loại phim (category).",
        "columns": {
            "film_id": "Mã bộ phim (khóa ngoại nối bảng film).",
            "category_id": "Mã thể loại (khóa ngoại nối bảng category).",
            "last_update": "Thời gian cập nhật gần nhất."
        }
    },
    "customer_list": {
        "description": "View tổng hợp danh sách chi tiết thông tin khách hàng kèm địa chỉ, thành phố, quốc gia và cửa hàng quản lý.",
        "columns": {
            "id": "Mã khách hàng (tương ứng customer_id).",
            "name": "Họ và tên đầy đủ của khách hàng.",
            "address": "Địa chỉ nhà/đường phố của khách hàng.",
            "zip code": "Mã bưu chính của khu vực khách hàng ở.",
            "phone": "Số điện thoại liên hệ của khách hàng.",
            "city": "Thành phố cư trú của khách hàng.",
            "country": "Quốc gia cư trú của khách hàng.",
            "notes": "Trạng thái tài khoản của khách hàng (active/in-active).",
            "sid": "Mã cửa hàng đăng ký thành viên (store_id)."
        }
    },
    "nicer_but_slower_film_list": {
        "description": "View danh sách phim được định dạng lại với tên diễn viên chuẩn hóa (viết hoa chữ cái đầu), thể loại phim, giá thuê và đánh giá.",
        "columns": {
            "fid": "Mã bộ phim (tương ứng film_id).",
            "title": "Tiêu đề bộ phim.",
            "description": "Tóm tắt nội dung phim.",
            "category": "Thể loại phim (Action, Comedy, Drama,...).",
            "price": "Giá thuê đĩa phim (USD).",
            "length": "Thời lượng phim (phút).",
            "rating": "Phân loại độ tuổi xem phim (G, PG, PG-13, R, NC-17).",
            "actors": "Danh sách các diễn viên tham gia bộ phim (đã định dạng chuẩn hóa tên)."
        }
    },
    "sales_by_film_category": {
        "description": "View báo cáo tổng doanh thu bán/cho thuê đĩa phim phân theo từng thể loại phim.",
        "columns": {
            "category": "Tên thể loại phim.",
            "total_sales": "Tổng doanh thu thu được từ thể loại phim tương ứng (USD)."
        }
    },
    "sales_by_store": {
        "description": "View báo cáo tổng doanh thu phân theo từng cửa hàng chi nhánh và quản lý cửa hàng.",
        "columns": {
            "store": "Tên địa điểm/thành phố và quốc gia nơi cửa hàng tọa lạc.",
            "manager": "Họ và tên người quản lý cửa hàng.",
            "total_sales": "Tổng doanh thu thu được của cửa hàng đó (USD)."
        }
    },
    "staff_list": {
        "description": "View tổng hợp danh sách thông tin chi tiết của nhân viên bao gồm địa chỉ, số điện thoại, thành phố và cửa hàng công tác.",
        "columns": {
            "id": "Mã định danh nhân viên (tương ứng staff_id).",
            "name": "Họ và tên đầy đủ của nhân viên.",
            "address": "Địa chỉ nhà của nhân viên.",
            "zip code": "Mã bưu chính của địa chỉ nhân viên.",
            "phone": "Số điện thoại liên lạc của nhân viên.",
            "city": "Thành phố nơi nhân viên sinh sống.",
            "country": "Quốc gia nơi nhân viên sinh sống.",
            "sid": "Mã chi nhánh cửa hàng nhân viên đang làm việc (store_id)."
        }
    }
}

print("🚀 Bắt đầu tự động đẩy toàn bộ Mô tả Tiếng Việt lên OpenMetadata Web UI...\n")

count_success = 0
for tbl_name, info in METADATA_DESCRIPTIONS.items():
    if tbl_name not in table_dict:
        continue
        
    tbl = table_dict[tbl_name]
    tbl_id = tbl["id"]
    columns = tbl.get("columns", [])
    
    patch_operations = []
    
    # 1. Thêm mô tả cho bảng
    patch_operations.append({
        "op": "add",
        "path": "/description",
        "value": info["description"]
    })
    
    # 2. Thêm mô tả cho từng cột
    for c_idx, col in enumerate(columns):
        c_name = col["name"]
        if c_name in info["columns"]:
            patch_operations.append({
                "op": "add",
                "path": f"/columns/{c_idx}/description",
                "value": info["columns"][c_name]
            })
            
    pr = requests.patch(
        f"{OPENMETADATA_API}/tables/{tbl_id}",
        json=patch_operations,
        headers=patch_headers
    )
    
    if pr.status_code == 200:
        count_success += 1
        print(f"   ✅ [{count_success}/{len(METADATA_DESCRIPTIONS)}] Bảng '{tbl_name}': Đã nạp thành công mô tả bảng + {len(patch_operations)-1} cột!")
    else:
        print(f"   ⚠️ Lỗi nạp bảng '{tbl_name}': Status {pr.status_code}")

print(f"\n🎉 HOÀN TẤT! Đã đẩy thành công mô tả tiếng Việt chuẩn nghiệp vụ cho {count_success} bảng lên OpenMetadata Web UI!")
