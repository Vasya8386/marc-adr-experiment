"""
check_groq_models.py
Kiểm tra CHÍNH XÁC danh sách model đang hoạt động trên Groq tại thời điểm hiện tại,
thay vì đoán tên (Groq đổi danh mục rất thường xuyên).

Cách chạy:
    set GROQ_API_KEY=xxxx
    python check_groq_models.py
"""
import os
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise SystemExit("Chưa set GROQ_API_KEY.")

r = requests.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
    timeout=30,
)
r.raise_for_status()
data = r.json()["data"]

print(f"Tổng số model đang khả dụng: {len(data)}\n")
print(f"{'MODEL ID':55s} {'OWNED BY':20s}")
print("-" * 75)
for m in sorted(data, key=lambda x: x["id"]):
    print(f"{m['id']:55s} {m.get('owned_by', ''):20s}")

print("\nGợi ý: chọn 2-4 model KHÁC HỌ nhau (khác owned_by hoặc khác kiến trúc rõ rệt) "
      "từ danh sách trên để đưa vào 2_generation_layer.py, tránh trùng với gpt-oss-120b/20b đã dùng.")
