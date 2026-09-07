import os
import networkx as nx
from typing import List, Dict, Any, Set
from app.metadata.openmetadata_client import om_client

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False


class SmartSchemaRetriever:
    """
    Graph-RAG Schema Retriever Engine:
    1. Vector DB (ChromaDB): Tìm kiếm ngữ nghĩa lấy các bảng hạt giống (Seed Tables).
    2. Graph DB (NetworkX): Duyệt đồ thị Khóa ngoại (Foreign Keys) để tự động nối bảng trung gian (Junction Tables).
    """

    def __init__(self):
        self.cache_data: Dict[str, Any] = {}
        self.schema_graph = nx.Graph()
        self.chroma_client = None
        self.collection = None
        self.initialized = False

    def _initialize_engines(self):
        """Khởi tạo Vector DB & Graph DB từ OpenMetadata Cache"""
        if self.initialized:
            return

        self.cache_data = om_client.load_local_cache()
        tables = self.cache_data.get("tables", {})

        # 1. Khởi tạo Graph DB (NetworkX) với các đỉnh là Bảng và các cạnh là Khóa ngoại (Foreign Keys)
        self.schema_graph.clear()
        for t_name, t_info in tables.items():
            self.schema_graph.add_node(t_name, description=t_info.get("description", ""))

            # Thêm các cạnh nối dựa trên Khóa ngoại (Foreign Keys)
            fks = t_info.get("foreign_keys", [])
            for fk in fks:
                target_table = fk.get("target_table")
                if target_table and target_table in tables:
                    self.schema_graph.add_edge(
                        t_name,
                        target_table,
                        fk_col=fk.get("columns", []),
                        pk_col=fk.get("target_column", "")
                    )

        # 2. Khởi tạo Vector DB (ChromaDB)
        if CHROMA_AVAILABLE:
            try:
                self.chroma_client = chromadb.Client()
                # Xóa collection cũ nếu tồn tại
                try:
                    self.chroma_client.delete_collection("schema_vectorstore")
                except Exception:
                    pass

                self.collection = self.chroma_client.create_collection(name="schema_vectorstore")

                documents = []
                metadatas = []
                ids = []

                for t_name, t_info in tables.items():
                    cols_desc = []
                    for c in t_info.get("columns", []):
                        cols_desc.append(f"{c.get('name')} ({c.get('type')}): {c.get('description', '')}")
                    
                    doc_text = f"Table {t_name}: {t_info.get('description', '')}. Columns: {', '.join(cols_desc)}"
                    documents.append(doc_text)
                    metadatas.append({"table_name": t_name})
                    ids.append(t_name)

                if documents:
                    self.collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )
                print("✨ [GRAPH-RAG ENGINE]: Đã khởi tạo thành công Vector DB (ChromaDB) & Graph DB (NetworkX)!")
            except Exception as e:
                print(f"[CẢNH BÁO VECTOR DB]: Lỗi khởi tạo ChromaDB ({e}), fallback sang Keyword/Graph Search.")

        self.initialized = True

    def _get_seed_tables_vector(self, question: str, top_k: int = 2) -> List[str]:
        """Bước 1: Dùng Vector DB (ChromaDB) để tìm các bảng hạt giống (Seed Tables) theo Cosine Similarity"""
        if self.collection:
            try:
                results = self.collection.query(
                    query_texts=[question],
                    n_results=top_k
                )
                if results and "metadatas" in results and results["metadatas"]:
                    seeds = [m["table_name"] for m in results["metadatas"][0]]
                    if seeds:
                        return seeds
            except Exception as e:
                print(f"[CẢNH BÁO VECTOR QUERY]: ({e})")

        # Fallback keyword matching nếu Vector DB chưa sẵn sàng
        tables = self.cache_data.get("tables", {})
        q_words = set(question.lower().split())
        scored = []
        for t_name, t_info in tables.items():
            text = (t_name + " " + t_info.get("description", "")).lower()
            score = sum(1 for kw in q_words if kw in text)
            if score > 0:
                scored.append((score, t_name))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]] if scored else ["film", "customer"]

    def _expand_tables_via_graph(self, seed_tables: List[str], max_tables: int = 4) -> List[str]:
        """Bước 2: Dùng Graph DB (NetworkX) tìm đường đi ngắn nhất để tự động thêm các bảng trung gian cần JOIN"""
        final_tables: Set[str] = set(seed_tables)

        if len(seed_tables) > 1:
            for i in range(len(seed_tables)):
                for j in range(i + 1, len(seed_tables)):
                    src = seed_tables[i]
                    dst = seed_tables[j]

                    if src in self.schema_graph and dst in self.schema_graph:
                        try:
                            path = nx.shortest_path(self.schema_graph, source=src, target=dst)
                            final_tables.update(path)
                        except nx.NetworkXNoPath:
                            pass
        
        result_list = list(final_tables)
        if len(result_list) > max_tables:
            # Ưu tiên các bảng hạt giống trước, sau đó lấy các bảng nối trung gian cận kề
            ordered = seed_tables + [t for t in result_list if t not in seed_tables]
            return ordered[:max_tables]
        return result_list

    def get_relevant_tables(self, question: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Lọc ra danh sách bảng liên quan nhất bằng quy trình Graph-RAG (Vector Search -> Graph Expansion)"""
        self._initialize_engines()
        tables = self.cache_data.get("tables", {})

        # 1. Vector Search lấy Seed Tables
        seed_names = self._get_seed_tables_vector(question, top_k=top_k)

        # 2. Graph Traversal lấy các bảng trung gian JOIN
        all_relevant_names = self._expand_tables_via_graph(seed_names)

        # 3. Trả về thông tin chi tiết bảng
        result_tables = [tables[name] for name in all_relevant_names if name in tables]
        return result_tables if result_tables else [tables.get("film")]

    def get_relevant_schema_context(self, question: str, top_k: int = 2) -> str:
        """Tạo chuỗi Context cho System Prompt cực gọn gàng bao gồm bảng hạt giống & bảng trung gian nối"""
        relevant_tables = self.get_relevant_tables(question, top_k=top_k)

        schema_lines = []
        for tbl in relevant_tables:
            t_name = tbl.get("name", "")
            t_desc = tbl.get("description", "")

            cols_desc = []
            for col in tbl.get("columns", []):
                c_name = col.get("name", "")
                c_type = col.get("type", "")
                cols_desc.append(f"{c_name} ({c_type})")

            fks_lines = []
            for fk in tbl.get("foreign_keys", []):
                fk_col = ", ".join(fk.get("columns", []))
                t_tbl = fk.get("target_table", "")
                t_col = fk.get("target_column", "")
                fks_lines.append(f"FK({fk_col})->{t_tbl}({t_col})")

            cols_str = ", ".join(cols_desc)
            fks_str = (" | " + ", ".join(fks_lines)) if fks_lines else ""
            desc_str = f" ({t_desc})" if t_desc else ""
            schema_lines.append(f"• BẢNG `{t_name}`{desc_str}:\n  Các cột: {cols_str}{fks_str}")

        return "\n\n".join(schema_lines)


# Instance singleton
schema_retriever = SmartSchemaRetriever()
