"""
1_2_manual_check_sample.py
BƯỚC 1.2 — Lấy ngẫu nhiên 10% ADR để kiểm tra thủ công xem regex có cắt đúng không.

Cách chạy:
    python 1_2_manual_check_sample.py

Kết quả:
    - sample_to_review.json  : danh sách mẫu cần bạn tự đọc và đánh giá
    - Sau khi đọc xong, mở file này lên, với mỗi mẫu bị cắt sai, ghi lại
      pattern nào trong 1_1_collect_adrs.py cần sửa (thường là do heading lạ).
"""
import json
import random

random.seed(42)  # để lần chạy lại vẫn ra cùng mẫu, tiện đối chiếu

with open("raw_adrs.json", "r", encoding="utf-8") as f:
    data = json.load(f)

sample_size = max(1, round(len(data) * 0.10))
sample = random.sample(data, sample_size)

for i, item in enumerate(sample, 1):
    item["_review_index"] = i
    item["_looks_ok"] = None          # bạn tự điền True/False sau khi đọc
    item["_note"] = ""                # ghi chú lỗi nếu có

with open("sample_to_review.json", "w", encoding="utf-8") as f:
    json.dump(sample, f, ensure_ascii=False, indent=2)

print(f"Đã lấy {sample_size}/{len(data)} mẫu (10%) để kiểm tra thủ công.")
print("Mở file sample_to_review.json, đọc từng context/decision, kiểm tra:")
print("  1. context có bị cắt cụt ở giữa câu không?")
print("  2. decision có lẫn nội dung của mục khác (Status, Consequences) không?")
print("  3. Điền True/False vào trường _looks_ok, ghi chú lỗi vào _note nếu có.")
