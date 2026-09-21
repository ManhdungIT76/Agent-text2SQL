# ⚡ Enterprise Text2SQL Deep Agent Platform

Hệ thống **Enterprise Text2SQL AI Agent Platform** chuyên sâu dành cho CSDL bán lẻ PostgreSQL (`dvdrental`), tích hợp toàn bộ hệ sinh thái tiên tiến: **OpenMetadata Governance**, **Graph-RAG Engine** (ChromaDB + NetworkX), **LangGraph Multi-Sub-Agents**, **Langfuse Cloud Observability**, **LLM-as-a-Judge Evaluation Pipeline** và **Streamlit Web UI**.

---

## 🚀 8 Hạng Mục Công Việc Đã Hoàn Thành (100% Micro-Phases)

| Bước | Hạng Mục Công Việc | Trạng Thái | Mô Tả Kỹ Thuật |
| :---: | :--- | :---: | :--- |
| **1** | OpenMetadata Client & Hybrid Disk Cache | ✅ **Hoàn thành** | Kết nối REST API `localhost:8585`, nạp mô tả Tiếng Việt & FKs, cache 24h tốc độ 0ms (giảm >93% token). |
| **2** | System Prompt Architecture v2.0 | ✅ **Hoàn thành** | Chuẩn Enterprise 8 thành phần với Few-Shot Demonstrations Tiếng Việt chuẩn hóa PostgreSQL. |
| **3** | Graph-RAG Engine | ✅ **Hoàn thành** | Kết hợp ChromaDB Vector DB + NetworkX Graph DB duyệt cây quan hệ FK (giảm >60% token context). |
| **4** | LangGraph Self-Correction Loop | ✅ **Hoàn thành** | Tự động bắt lỗi thực thi PostgreSQL và đưa Traceback vào LLM sửa lỗi thử lại tối đa 3 lần. |
| **5** | Langfuse Cloud Observability | ✅ **Hoàn thành** | Giám sát Traces, Latency (ms), Token Usage và Prompt Governance trên Langfuse Cloud Dashboard. |
| **6** | LLM-as-a-Judge Evaluation Pipeline | ✅ **Hoàn thành** | Script `run_eval.py` tự động chấm điểm SQL 1-5 theo 4 tiêu chí và đồng bộ Scores lên Langfuse. |
| **7** | Multi-Sub-Agents & Strict Read-Only Security | ✅ **Hoàn thành** | Phân rã 3 Sub-Agents chuyên biệt (`Schema Analyst`, `SQL Specialist`, `Safety Assessor`) chặn 100% DML/DDL. |
| **8** | Streamlit Web UI Application | ✅ **Hoàn thành** | Giao diện Chatbot, SQL Inspector, Bảng dữ liệu Pandas DataFrame tương tác & Tải xuất CSV 100% Tiếng Việt. |

---

## 🛠️ Hướng Dẫn Khởi Chạy Hệ Thống

### 1. Khởi Động Cụm Docker Container Services
```powershell
docker-compose up -d
```
Cụm Services sẽ được khởi chạy ngầm:
- **PostgreSQL Database**: `localhost:5433` (Database: `dvdrental`)
- **OpenMetadata Server**: `http://localhost:8585` (Email: `admin@open-metadata.org`, Pass: `admin`)
- **OpenSearch Engine**: `localhost:9200`

### 2. Khởi Chạy Giao Diện Web UI Streamlit (Ứng Dụng Chính)
```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python312\Scripts\streamlit.exe" run app_streamlit.py
```
Trình duyệt sẽ tự động mở giao diện tại `http://localhost:8501`.

### 3. Chạy Pipeline Đánh Giá Tự Động (LLM-as-a-Judge & Langfuse Score Sync)
```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe" run_eval.py
```

---

## 📁 Cấu Trúc Mã Nguồn Dự Án

```text
text2sql-agent/
│
├── app/
│   ├── agent/             # Multi-Sub-Agents & LangGraph StateGraph Workflow
│   │   ├── sub_agents.py  # 3 Sub-Agents: Schema Analyst, SQL Specialist, Safety Assessor
│   │   └── graph.py       # LangGraph Checkpointer, Self-Correction Loop & Security Policy
│   │
│   ├── metadata/          # OpenMetadata REST API Client & Graph-RAG Engine
│   │   ├── openmetadata_client.py  # REST API Client & Disk Cache 24h
│   │   ├── schema_cache.json       # Schema Cache Local 22 Bảng & Views
│   │   └── schema_retriever.py     # ChromaDB Vector Store + NetworkX Graph DB
│   │
│   ├── llm/               # System Prompt Architecture v2.0 & LLM Cloud API (Groq / Gemini)
│   ├── database/          # Connection pool & Executor trả về kết quả bảng Dicts
│   ├── eval/              # Execution Validator & LLM-as-a-Judge Engine (1-5 điểm)
│   └── config.py          # Quản lý cấu hình biến môi trường
│
├── app_streamlit.py       # 🌐 ỨNG DỤNG WEB UI DÀNH CHO NGƯỜI DÙNG (Streamlit 100% Tiếng Việt)
├── run_eval.py            # 📊 SCRIPT ĐÁNH GIÁ TỰ ĐỘNG VÀ ĐỒNG BỘ SCORE VỀ LANGFUSE CLOUD
├── tests/test_dataset.json# 🧪 Bộ dữ liệu testcase kiểm thử 5 kịch bản thực tế
├── PROGRESS.md            # 📝 Nhật ký tiến độ chi tiết 8 Micro-Phases
├── requirements.txt       # Danh sách gói phụ thuộc Python
└── docker-compose.yml     # Cấu hình 4 Docker containers
```
