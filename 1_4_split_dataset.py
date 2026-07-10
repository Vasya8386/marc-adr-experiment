"""
1_4_split_dataset.py
BƯỚC 1.4 — Tách gold test set (đánh giá) và RAG knowledge base pool (không trùng nhau)

Cách chạy:
    python 1_4_split_dataset.py

Kết quả:
    - gold_test_set.json   : 30-40 ADR dùng để ĐÁNH GIÁ (không đưa vào RAG)
    - rag_pool.json        : phần còn lại, dùng làm knowledge base cho Retrieval Layer
    - split_summary.csv    : thống kê phân bố nhóm G1-G7 ở mỗi tập, để kiểm tra cân bằng
"""
import json
import random
import csv
from collections import defaultdict

random.seed(42)

IN_FILE = "labeled_adrs.json"
TEST_SIZE = 35          # nằm trong khoảng đề xuất 30-40
PRIORITY_KEYWORD = "considered option"  # ưu tiên ADR có phần "Considered Options" vào test set

with open(IN_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Nhóm theo G1-G7 để lấy đều mỗi nhóm ~5 mẫu vào test set (35/7=5)
by_group = defaultdict(list)
for item in data:
    by_group[item["group"]].append(item)

test_set = []
per_group_quota = max(1, TEST_SIZE // len(by_group))

for group, items in by_group.items():
    # ưu tiên item có "considered option" trong context/decision
    items_sorted = sorted(
        items,
        key=lambda x: PRIORITY_KEYWORD in ((x.get("context", "") + x.get("decision", "")).lower()),
        reverse=True,
    )
    picked = items_sorted[:per_group_quota]
    test_set.extend(picked)

# nếu chưa đủ TEST_SIZE (do nhóm nào đó ít mẫu), lấy bù ngẫu nhiên từ phần còn lại
test_urls = {item["url"] for item in test_set}
remaining = [item for item in data if item["url"] not in test_urls]
random.shuffle(remaining)
while len(test_set) < TEST_SIZE and remaining:
    extra = remaining.pop()
    test_set.append(extra)
    test_urls.add(extra["url"])

rag_pool = [item for item in data if item["url"] not in test_urls]

with open("gold_test_set.json", "w", encoding="utf-8") as f:
    json.dump(test_set, f, ensure_ascii=False, indent=2)
with open("rag_pool.json", "w", encoding="utf-8") as f:
    json.dump(rag_pool, f, ensure_ascii=False, indent=2)

# thống kê
summary = defaultdict(lambda: {"test": 0, "rag_pool": 0})
for item in test_set:
    summary[item["group"]]["test"] += 1
for item in rag_pool:
    summary[item["group"]]["rag_pool"] += 1

with open("split_summary.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["group", "test_set", "rag_pool"])
    for g, counts in summary.items():
        writer.writerow([g, counts["test"], counts["rag_pool"]])

print(f"Test set: {len(test_set)} ADR  |  RAG pool: {len(rag_pool)} ADR")
print("\nPhân bố theo nhóm (test / rag_pool):")
for g, counts in summary.items():
    print(f"  {g}: {counts['test']} / {counts['rag_pool']}")

# kiểm tra chéo: đảm bảo không có URL trùng giữa 2 tập
overlap = test_urls.intersection({item["url"] for item in rag_pool})
if overlap:
    print(f"\n[CẢNH BÁO] Phát hiện {len(overlap)} ADR bị trùng giữa test set và RAG pool!")
else:
    print("\n[OK] Không có rò rỉ dữ liệu giữa test set và RAG pool.")
