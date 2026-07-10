"""
1_1_collect_adrs_batch5_targeted.py
BƯỚC 1.1 (BATCH 5 — NHẮM MỤC TIÊU) — Chỉ tìm thêm ADR cho 2 nhóm đang thiếu nặng:
G4_APIGatewayDiscovery (3) và G6_Resilience (3).
Dùng search query chứa từ khóa đặc trưng của 2 nhóm này, rồi lọc thêm bằng keyword-score
để CHỈ giữ lại kết quả thực sự thuộc G4/G6 (tránh làm G1/G7 vốn đã thừa phình to thêm).

Cách chạy:
    python 1_1_collect_adrs_batch5_targeted.py

Kết quả: nối thêm vào raw_adrs.json (chỉ thêm bản ghi mới, có trường "group" gán sẵn
để không phải chạy lại toàn bộ 1_3_label_groups.py cho 120 ADR cũ)
"""
import os
import re
import json
import time
from github import Github, GithubException, RateLimitExceededException

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise SystemExit("Chưa set GITHUB_TOKEN.")

g = Github(GITHUB_TOKEN)

# Truy vấn nhắm thẳng vào từ khóa đặc trưng G4 và G6
SEARCH_QUERIES = [
    ('"circuit breaker" "## Decision" extension:md', "G6_Resilience"),
    ('"circuit breaker" "## Context" extension:md', "G6_Resilience"),
    ('"retry" "fallback" "## Decision" extension:md', "G6_Resilience"),
    ('"API gateway" "## Decision" extension:md', "G4_APIGatewayDiscovery"),
    ('"service discovery" "## Decision" extension:md', "G4_APIGatewayDiscovery"),
    ('"rate limiting" "## Context" extension:md', "G4_APIGatewayDiscovery"),
    ('"backend for frontend" extension:md', "G4_APIGatewayDiscovery"),
]

MAX_RESULTS_PER_QUERY = 30
TARGET_PER_GROUP = 15   # dừng riêng từng nhóm khi đủ 15

GROUP_KEYWORDS = {
    "G4_APIGatewayDiscovery": ["api gateway", "service discovery", "routing",
                                "load balancer", "rate limit", "backend for frontend"],
    "G6_Resilience": ["circuit breaker", "retry", "bulkhead", "timeout", "resilience",
                       "fallback", "fault tolerance"],
}

CONTEXT_PATTERNS = [
    r"##\s*Context(?:\s+and\s+Problem\s+Statement)?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"\*\*Context\*\*\s*\n+(.*?)(?=\n\*\*|\Z)",
    r"##\s*Decision\s+Drivers?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"#\s*Context\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Problem\s+Statement\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Background\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Motivation\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
]
DECISION_PATTERNS = [
    r"##\s*Decision(?:\s+Outcome)?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"\*\*Decision\*\*\s*\n+(.*?)(?=\n\*\*|\Z)",
    r"##\s*Chosen\s+Option\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"#\s*Decision\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Proposal\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Solution\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
]


def extract_context_decision(content_str):
    context, decision = None, None
    for pat in CONTEXT_PATTERNS:
        m = re.search(pat, content_str, re.DOTALL | re.IGNORECASE)
        if m:
            context = m.group(1).strip()
            break
    for pat in DECISION_PATTERNS:
        m = re.search(pat, content_str, re.DOTALL | re.IGNORECASE)
        if m:
            decision = m.group(1).strip()
            break
    return {"context": context, "decision": decision}


def score_for_group(text, group):
    text = text.lower()
    return sum(text.count(kw) for kw in GROUP_KEYWORDS[group])


def safe_search(query, max_results):
    results = []
    try:
        paginated = g.search_code(query=query)
        for i, item in enumerate(paginated):
            if i >= max_results:
                break
            results.append(item)
            time.sleep(2.5)
    except RateLimitExceededException:
        print("    [RATE LIMIT] đợi 60s...")
        time.sleep(60)
    except GithubException as e:
        print(f"    [LỖI SEARCH] query='{query}': {e}")
    return results


def main():
    with open("labeled_adrs.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
    existing_urls = {item["url"] for item in dataset}
    start_count = len(dataset)

    group_counts = {}
    for item in dataset:
        group_counts[item["group"]] = group_counts.get(item["group"], 0) + 1

    added = 0
    for query, target_group in SEARCH_QUERIES:
        if group_counts.get(target_group, 0) >= TARGET_PER_GROUP:
            print(f"[BỎ QUA] {target_group} đã đủ {TARGET_PER_GROUP} — không cần query '{query}'")
            continue

        print(f"\n[TÌM KIẾM cho {target_group}] {query}")
        items = safe_search(query, MAX_RESULTS_PER_QUERY)
        print(f"    -> {len(items)} file khớp")

        for item in items:
            if group_counts.get(target_group, 0) >= TARGET_PER_GROUP:
                break
            if item.html_url in existing_urls:
                continue

            try:
                content_str = item.decoded_content.decode("utf-8", errors="ignore")
                extracted = extract_context_decision(content_str)

                if extracted["context"] and len(extracted["context"]) >= 100 and extracted["decision"]:
                    full_text = extracted["context"] + " " + extracted["decision"]
                    # chỉ giữ nếu điểm khớp nhóm mục tiêu thực sự cao nhất trong 2 nhóm đang thiếu
                    score_g4 = score_for_group(full_text, "G4_APIGatewayDiscovery")
                    score_g6 = score_for_group(full_text, "G6_Resilience")
                    best_group = "G4_APIGatewayDiscovery" if score_g4 >= score_g6 else "G6_Resilience"

                    if best_group != target_group or max(score_g4, score_g6) == 0:
                        continue  # không thực sự thuộc nhóm cần, bỏ qua để tránh nhiễu

                    dataset.append({
                        "repo": item.repository.full_name,
                        "file": item.name,
                        "path": item.path,
                        "url": item.html_url,
                        "context": extracted["context"],
                        "decision": extracted["decision"],
                        "context_length": len(extracted["context"]),
                        "group": target_group,
                    })
                    existing_urls.add(item.html_url)
                    group_counts[target_group] = group_counts.get(target_group, 0) + 1
                    added += 1
                time.sleep(0.3)
            except RateLimitExceededException:
                print("    [RATE LIMIT nội dung] đợi 30s...")
                time.sleep(30)
            except Exception as e:
                print(f"    lỗi đọc {item.path}: {e}")

    with open("labeled_adrs.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n=== TÓM TẮT BATCH 5 ===")
    print(f"ADR trước: {start_count}  ->  Tổng sau: {len(dataset)}  (+{added})")
    print("\nPhân bố cập nhật:")
    for g_name, c in sorted(group_counts.items()):
        flag = "  << VẪN THIẾU" if c < 15 else ""
        print(f"  {g_name}: {c}{flag}")


if __name__ == "__main__":
    main()
