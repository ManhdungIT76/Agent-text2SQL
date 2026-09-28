import os
import sys
import json
import time
from typing import List, Dict, Any

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import config
from app.metadata.openmetadata_client import om_client
from app.agent.graph import text2sql_agent_graph, get_langfuse_handler
from app.eval.evaluator import evaluator
from langfuse import Langfuse


def load_dataset(filepath: str = "tests/test_dataset.json") -> List[Dict[str, Any]]:
    if not os.path.exists(filepath):
        print(f"❌ Không tìm thấy file dataset kiểm thử tại {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def run_evaluation_pipeline():
    print("\n" + "=" * 80)
    print("📊 [AUTOMATED EVALUATION PIPELINE]: TEXT2SQL LLM-AS-A-JUDGE & LANGFUSE SCORES")
    print("=" * 80 + "\n")

    # 1. Nạp cache OpenMetadata
    om_client.load_local_cache()

    # 2. Khởi tạo Langfuse Client cho việc đẩy điểm (Score Sync)
    langfuse_client = None
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            langfuse_client = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST
            )
            print("🚀 [LANGFUSE INTEGRATION]: Đã kết nối thành công Langfuse Cloud cho Score Sync.")
        except Exception as e:
            print(f"⚠️ [LANGFUSE WARNING]: Không thể kết nối Langfuse Client ({e})")

    # 3. Đọc bộ dữ liệu kiểm thử
    dataset = load_dataset("tests/test_dataset.json")
    if not dataset:
        print("❌ Dataset rỗng hoặc không hợp lệ. Dừng chương trình.")
        return

    results = []

    for idx, item in enumerate(dataset, 1):
        tc_id = item.get("id", f"TC{idx:02d}")
        question = item["question"]
        golden_sql = item.get("golden_sql", "")
        category = item.get("category", "general")

        print("-" * 80)
        print(f"🧪 [{tc_id}] Category: {category}")
        print(f"❓ Câu hỏi: \"{question}\"")
        print(f"🎯 Golden SQL: {golden_sql}")

        # Khởi tạo CallbackHandler mới cho từng lượt test
        langfuse_handler = get_langfuse_handler()
        run_config = {}
        if langfuse_handler:
            run_config["callbacks"] = [langfuse_handler]

        initial_state = {
            "question": question,
            "schema_context": "",
            "sql": "",
            "query_result": None,
            "error_message": None,
            "retry_count": 0,
            "max_retries": 3
        }

        start_time = time.time()
        final_state = text2sql_agent_graph.invoke(initial_state, config=run_config)
        latency_ms = round((time.time() - start_time) * 1000, 2)

        generated_sql = final_state.get("sql", "")
        schema_context = final_state.get("schema_context", "")

        print(f"🤖 Generated SQL: {generated_sql}")
        print(f"⏱️ Latency: {latency_ms} ms")

        # 4. Đánh giá tính hợp lệ thực thi PostgreSQL
        exec_eval = evaluator.evaluate_execution(generated_sql, golden_sql)
        print(f"⚡ Status thực thi: {'✅ THÀNH CÔNG' if exec_eval['exec_success'] else '❌ THẤT BẠI'} (Số dòng: {exec_eval['row_count']})")
        if exec_eval.get("error"):
            print(f"   ⚠️ Lỗi: {exec_eval['error']}")

        # 5. Đánh giá bằng LLM-as-a-Judge
        print("🧠 [LLM-AS-A-JUDGE]: Đang chấm điểm chất lượng SQL...")
        judge_eval = evaluator.evaluate_with_llm_judge(
            question=question,
            generated_sql=generated_sql,
            golden_sql=golden_sql,
            exec_result=exec_eval,
            schema_context=schema_context
        )

        overall_score = judge_eval.get("score", 0.0)
        reasoning = judge_eval.get("reasoning", "")
        print(f"⭐ Điểm LLM Judge: {overall_score} / 5.0")
        print(f"📝 Lý do: {reasoning}")

        # 6. Đồng bộ Scores lên Langfuse Dashboard nếu có CallbackHandler & Trace ID
        trace_id = None
        if langfuse_handler and hasattr(langfuse_handler, 'get_trace_id'):
            try:
                trace_id = langfuse_handler.get_trace_id()
            except Exception:
                pass

        if langfuse_client and trace_id:
            try:
                # Đẩy điểm LLM Judge Score
                langfuse_client.score(
                    trace_id=trace_id,
                    name="llm_judge_score",
                    value=overall_score,
                    comment=reasoning
                )
                # Đẩy điểm Trạng thái thực thi SQL (1.0 thành công, 0.0 thất bại)
                langfuse_client.score(
                    trace_id=trace_id,
                    name="execution_success",
                    value=1.0 if exec_eval["exec_success"] else 0.0,
                    comment=exec_eval.get("error", "OK")
                )
                # Đẩy điểm Khớp kết quả Golden Data (1.0 thành công, 0.0 thất bại)
                langfuse_client.score(
                    trace_id=trace_id,
                    name="data_accuracy",
                    value=1.0 if exec_eval.get("matches_golden") else 0.0
                )
                print(f"☁️ [LANGFUSE SYNC]: Đã đồng bộ Scores thành công cho Trace ID: {trace_id}")
            except Exception as se:
                print(f"⚠️ [LANGFUSE SYNC ERROR]: Không thể gửi score ({se})")

        results.append({
            "id": tc_id,
            "question": question,
            "generated_sql": generated_sql,
            "exec_success": exec_eval["exec_success"],
            "row_count": exec_eval["row_count"],
            "matches_golden": exec_eval["matches_golden"],
            "judge_score": overall_score,
            "latency_ms": latency_ms,
            "reasoning": reasoning
        })

        time.sleep(1.5)

    # Flush Langfuse client queue nếu có
    if langfuse_client:
        try:
            langfuse_client.flush()
        except Exception:
            pass

    # 7. In Báo cáo tổng hợp
    print("\n" + "=" * 80)
    print("📈 [BÁO CÁO TỔNG HỢP KẾT QUẢ ĐÁNH GIÁ - TEXT2SQL AGENT EVALUATION REPORT]")
    print("=" * 80)

    total_tests = len(results)
    exec_success_count = sum(1 for r in results if r["exec_success"])
    golden_match_count = sum(1 for r in results if r["matches_golden"])
    avg_score = round(sum(r["judge_score"] for r in results) / total_tests, 2) if total_tests > 0 else 0
    avg_latency = round(sum(r["latency_ms"] for r in results) / total_tests, 2) if total_tests > 0 else 0
    exec_rate = round((exec_success_count / total_tests) * 100, 1) if total_tests > 0 else 0

    print(f"📊 Tổng số Test cases:       {total_tests}")
    print(f"✅ Tỷ lệ Thực thi thành công:  {exec_rate}% ({exec_success_count}/{total_tests})")
    print(f"🎯 Khớp dữ liệu Golden SQL:   {golden_match_count}/{total_tests}")
    print(f"⭐ Điểm LLM Judge trung bình: {avg_score} / 5.0")
    print(f"⏱️ Độ trễ trung bình:         {avg_latency} ms")
    print("-" * 80)

    print("\n📋 CHI TIẾT THEO BẢNG TEST CASE:")
    header = f"| {'ID':<6} | {'Exec':<6} | {'Match':<6} | {'Score':<6} | {'Latency':<9} | {'Lý do / Phản hồi của LLM Judge':<40} |"
    print(header)
    print("|" + "-" * 8 + "|" + "-" * 8 + "|" + "-" * 8 + "|" + "-" * 8 + "|" + "-" * 11 + "|" + "-" * 42 + "|")

    for r in results:
        exec_str = "PASS" if r["exec_success"] else "FAIL"
        match_str = "YES" if r["matches_golden"] else "NO"
        reason_short = (r["reasoning"][:38] + "..") if len(r["reasoning"]) > 40 else r["reasoning"]
        row = f"| {r['id']:<6} | {exec_str:<6} | {match_str:<6} | {r['judge_score']:<6.1f} | {r['latency_ms']:<7.1f}ms | {reason_short:<40} |"
        print(row)

    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_evaluation_pipeline()
