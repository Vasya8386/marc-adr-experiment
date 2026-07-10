"""
1_3_label_groups.py
BƯỚC 1.3 — Gán nhãn G1-G7 bán tự động (gợi ý bằng keyword-score, bạn xác nhận/sửa thủ công)

Cách chạy:
    python 1_3_label_groups.py

Cách dùng:
    Với mỗi ADR, script tính điểm khớp keyword cho cả 7 nhóm và ĐỀ XUẤT nhóm điểm cao nhất.
    Bạn gõ:
      - Enter          -> đồng ý với đề xuất
      - 1-7             -> chọn nhóm khác thủ công
      - s               -> bỏ qua (không thuộc nhóm nào rõ ràng -> loại khỏi dataset)
      - q               -> lưu và thoát giữa chừng (chạy lại sẽ tiếp tục từ chỗ dừng)

Kết quả:
    - labeled_adrs.json : ADR đã có trường "group" (G1..G7)
"""
import json
import os

GROUP_KEYWORDS = {
    "G1_ServiceDecomposition": ["service boundary", "decompose", "bounded context",
                                 "monolith", "split service", "domain-driven"],
    "G2_Communication": ["sync", "async", "message queue", "event-driven", "rest api",
                          "grpc", "pub/sub", "kafka", "nats", "rabbitmq"],
    "G3_DataManagement": ["database per service", "saga", "cqrs", "event sourcing",
                           "schema", "outbox", "transactional", "cdc"],
    "G4_APIGatewayDiscovery": ["api gateway", "service discovery", "routing",
                                "load balancer", "rate limit", "backend for frontend"],
    "G5_DeploymentOrchestration": ["kubernetes", "helm", "docker", "container",
                                    "deployment", "scaling", "orchestration", "ci/cd"],
    "G6_Resilience": ["circuit breaker", "retry", "bulkhead", "timeout", "resilience",
                       "fallback", "fault tolerance"],
    "G7_ObservabilitySecurity": ["logging", "tracing", "metrics", "observability",
                                  "auth", "jwt", "oauth", "secret management", "vault"],
}

IN_FILE = "raw_adrs.json"
OUT_FILE = "labeled_adrs.json"


def score_groups(text):
    text = text.lower()
    scores = {}
    for group, kws in GROUP_KEYWORDS.items():
        scores[group] = sum(text.count(kw) for kw in kws)
    return scores


def main():
    with open(IN_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    labeled = []
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            labeled = json.load(f)
    done_urls = {item["url"] for item in labeled}

    group_names = list(GROUP_KEYWORDS.keys())

    for item in data:
        if item["url"] in done_urls:
            continue

        text = (item.get("context", "") or "") + " " + (item.get("decision", "") or "")
        scores = score_groups(text)
        suggested = max(scores, key=scores.get)
        suggested_idx = group_names.index(suggested) + 1

        print("\n" + "=" * 70)
        print(f"Repo: {item['repo']}  |  File: {item['file']}")
        print(f"Context: {item['context'][:300]}...")
        print(f"Decision: {(item.get('decision') or '')[:200]}...")
        print("-" * 70)
        for i, g in enumerate(group_names, 1):
            marker = " <== đề xuất" if g == suggested else ""
            print(f"  {i}. {g} (score={scores[g]}){marker}")
        choice = input(f"Chọn nhóm [Enter={suggested_idx}, 1-7, s=skip, q=quit]: ").strip().lower()

        if choice == "q":
            break
        if choice == "s":
            continue
        if choice == "":
            item["group"] = suggested
        elif choice.isdigit() and 1 <= int(choice) <= 7:
            item["group"] = group_names[int(choice) - 1]
        else:
            print("Lựa chọn không hợp lệ, bỏ qua mẫu này.")
            continue

        labeled.append(item)
        # lưu tăng dần để không mất dữ liệu nếu bị ngắt giữa chừng
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(labeled, f, ensure_ascii=False, indent=2)

    print(f"\nĐã gán nhãn {len(labeled)} ADR. Lưu tại {OUT_FILE}")
    counts = {}
    for item in labeled:
        counts[item["group"]] = counts.get(item["group"], 0) + 1
    print("\nPhân bố theo nhóm:")
    for g in group_names:
        flag = "  << CẦN THÊM (mục tiêu >=15)" if counts.get(g, 0) < 15 else ""
        print(f"  {g}: {counts.get(g, 0)}{flag}")


if __name__ == "__main__":
    main()
