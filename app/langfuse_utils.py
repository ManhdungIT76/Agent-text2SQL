"""
Langfuse Singleton Module - Quản lý tập trung kết nối Langfuse
===============================================================
- get_langfuse_client()    → Singleton Langfuse SDK client (dùng chung cho Prompt Governance & Score Sync)
- create_trace_handler()   → Tạo CallbackHandler cho LangChain tracing với metadata nhất quán
- flush_all()              → Flush tất cả pending traces lên Langfuse Cloud
- check_langfuse_connection() → Kiểm tra kết nối thực tế tới Langfuse Server
"""

import os
import threading
from typing import Optional, Any

_langfuse_client = None
_langfuse_lock = threading.Lock()
_active_handlers = []


def _ensure_env_vars():
    """Đảm bảo env vars được set cho Langfuse SDK (chỉ set 1 lần)"""
    from app.config import config
    if config.LANGFUSE_PUBLIC_KEY and not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        os.environ["LANGFUSE_PUBLIC_KEY"] = config.LANGFUSE_PUBLIC_KEY
    if config.LANGFUSE_SECRET_KEY and not os.environ.get("LANGFUSE_SECRET_KEY"):
        os.environ["LANGFUSE_SECRET_KEY"] = config.LANGFUSE_SECRET_KEY
    if config.LANGFUSE_HOST:
        os.environ["LANGFUSE_HOST"] = config.LANGFUSE_HOST
        os.environ["LANGFUSE_BASE_URL"] = config.LANGFUSE_HOST
    timeout_val = getattr(config, "LANGFUSE_TIMEOUT", 15)
    os.environ["LANGFUSE_TIMEOUT"] = str(timeout_val)


def get_langfuse_client():
    """
    Trả về singleton Langfuse SDK client.
    Dùng chung cho: Prompt Governance (.get_prompt), Score Sync (.score), và Tracing.
    Thread-safe với lock.
    """
    global _langfuse_client

    from app.config import config
    if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
        return None

    if _langfuse_client is not None:
        return _langfuse_client

    with _langfuse_lock:
        # Double-check sau khi acquire lock
        if _langfuse_client is not None:
            return _langfuse_client

        try:
            _ensure_env_vars()
            from langfuse import Langfuse
            timeout_val = getattr(config, "LANGFUSE_TIMEOUT", 15)
            _langfuse_client = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST,
                timeout=timeout_val
            )
            print("[LANGFUSE] Client initialized.")
            return _langfuse_client
        except Exception as e:
            print(f"[LANGFUSE ERROR] Failed to initialize client: {e}")
            return None


def create_trace_handler(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_name: Optional[str] = None,
    tags: Optional[list] = None
) -> Optional[Any]:
    """
    Tạo CallbackHandler cho LangChain/LangGraph tracing.
    Langfuse SDK v4+ đọc secret_key, host từ env vars.
    CallbackHandler chỉ nhận public_key làm kwarg.

    Args:
        session_id: ID phiên làm việc (nhóm các traces cùng session lại)
        user_id: ID người dùng
        trace_name: Tên trace hiển thị trên Dashboard
        tags: Danh sách tags để phân loại
    """
    from app.config import config
    if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
        return None

    try:
        # Đảm bảo env vars được set trước khi tạo handler
        _ensure_env_vars()

        try:
            from langfuse.langchain import CallbackHandler
            # SDK v4+: CallbackHandler chỉ nhận public_key, đọc secret_key/host từ env vars
            handler = CallbackHandler(public_key=config.LANGFUSE_PUBLIC_KEY)
        except (TypeError, ImportError):
            # TypeError: SDK cũ hơn không nhận public_key kwarg
            # ImportError: SDK thiếu module (vd: propagate_attributes trên Python 3.12)
            try:
                from langfuse.langchain import CallbackHandler
                handler = CallbackHandler()
            except (ImportError, Exception):
                return None

        _active_handlers.append(handler)
        return handler

    except Exception as e:
        print(f"[LANGFUSE HANDLER WARN]: CallbackHandler unavailable ({e})")
        return None


def flush_all():
    """
    Flush tất cả pending traces lên Langfuse Cloud Server.
    Gọi hàm này SAU KHI hoàn tất xử lý 1 câu hỏi/pipeline.
    """
    global _active_handlers

    # 1. Flush tất cả active handlers
    for handler in _active_handlers:
        try:
            if hasattr(handler, "langfuse"):
                handler.langfuse.flush()
            elif hasattr(handler, "flush"):
                handler.flush()
        except Exception:
            pass
    _active_handlers.clear()

    # 2. Flush singleton client
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception:
            pass


def check_langfuse_connection() -> bool:
    """
    Kiểm tra kết nối thực tế tới Langfuse Server.
    Trả về True nếu kết nối thành công, False nếu không.
    """
    from app.config import config
    if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
        return False

    try:
        import requests
        host = config.LANGFUSE_HOST.rstrip("/")
        resp = requests.get(f"{host}/api/public/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        # Fallback: thử khởi tạo client để kiểm tra
        try:
            client = get_langfuse_client()
            return client is not None
        except Exception:
            return False
