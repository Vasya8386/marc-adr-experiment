"""
2b_cleanup_empty_results.py
Xóa các bản ghi có generated_decision rỗng/quá ngắn (do lỗi reasoning model chiếm hết token)
khỏi generation_results.json, để checkpoint tự động sinh lại đúng những tổ hợp đó.

Cách chạy:
    python 2b_cleanup_empty_results.py
"""
import json

with open("generation_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

before = len(results)
cleaned = [r for r in results if r.get("generated_decision") and len(r["generated_decision"].strip()) >= 10]
removed = before - len(cleaned)

with open("generation_results.json", "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

print(f"Trước: {before} bản ghi -> Sau khi dọn: {len(cleaned)} bản ghi (đã xóa {removed} bản ghi rỗng/quá ngắn)")
print("Chạy lại '2_generation_layer.py' để tự động sinh lại các bản ghi vừa bị xóa với cấu hình mới.")
