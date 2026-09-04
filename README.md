# Agent-text2SQL (Enterprise Text2SQL Agent & OpenMetadata Governance)

Hệ thống AI Text-to-SQL cho dữ liệu bán lẻ PostgreSQL (`dvdrental`), tích hợp LangChain, Google Gemini LLM và Quản trị Dữ liệu Metadata Store **OpenMetadata**.

## 🚀 Tính năng nổi bật

- **Quản trị Dữ liệu với OpenMetadata**: Tự động thu thập Metadata, nạp và đồng bộ Mô tả Tiếng Việt (Business Descriptions) cho 20/20 Bảng và Views.
- **RAG & Metadata Context Selection**: Rút trích danh sách bảng, kiểu dữ liệu và mô tả từ OpenMetadata để làm ngữ cảnh sinh SQL chuẩn xác cho LLM.
- **Text-to-SQL Execution Engine**: Chuyển đổi câu hỏi tiếng Việt thành câu lệnh SQL và thực thi trực tiếp trên PostgreSQL Docker Container.
- **Tương thích Quy trình Deep Agent & LangGraph**: Thiết kế sẵn cho mở rộng LangGraph State Management, Pack & Stream API Mode.

## 📁 Cấu trúc thư mục

```
Agent-text2SQL/
│
├── app/
│   ├── database/
│   │   ├── connection.py   # Khởi tạo kết nối PostgreSQL
│   │   ├── schema.py       # Định nghĩa Schema thông tin các bảng dữ liệu
│   │   └── executor.py     # Thực thi các truy vấn SQL lên PostgreSQL Docker
│   │
│   ├── llm/
│   │   ├── client.py       # Tích hợp Gemini LLM & sinh SQL bằng LangChain
│   │   └── prompts.py      # Cấu hình System Prompt v1.0 design pattern
│   │
│   ├── config.py           # Quản lý cấu hình & biến môi trường (.env)
│   └── main.py             # Luồng chính xử lý từ câu hỏi đến kết quả
│
├── auto_describe_all.py    # Script nạp Mô tả Tiếng Việt cho 20 Bảng/View lên OpenMetadata API
├── demo_workflow.py        # Demo quy trình 4 bước: User Input -> OpenMetadata -> LLM SQL -> PostgreSQL Data
├── docker-compose.yml      # Cấu hình cụm Docker: Postgres (5433), OpenMetadata (8585), OpenSearch (9200), Ingestion (8080)
├── init-db/
│   ├── 01-create-openmetadata-db.sql
│   └── dvdrental.sql       # CSDL mẫu dvdrental
│
├── requirements.txt        # Các thư viện phụ thuộc Python
├── .env.example            # Mẫu cấu hình môi trường
└── README.md
```

## 🛠️ Hướng dẫn Khởi chạy

### 1. Khởi động Cụm Docker Service
```bash
docker-compose up -d
```
Hệ thống sẽ chạy các container:
- **PostgreSQL**: `localhost:5433` (DB: `dvdrental`)
- **OpenMetadata Web UI**: `http://localhost:8585` (Email: `admin@open-metadata.org`, Pass: `admin`)
- **OpenSearch**: `localhost:9200`

### 2. Kích hoạt Môi trường ảo & Cài đặt Thư viện
```bash
.\.agent\Scripts\activate
pip install -r requirements.txt
```

### 3. Nạp Mô tả Tiếng Việt lên OpenMetadata
```bash
python auto_describe_all.py
```

### 4. Chạy Demo Luồng Tích hợp Text2SQL + OpenMetadata
```bash
python demo_workflow.py
```
