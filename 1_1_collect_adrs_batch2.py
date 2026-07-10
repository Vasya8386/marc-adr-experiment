"""
1_1_collect_adrs_batch2.py
BƯỚC 1.1 (BATCH 2) — Quét thêm 20 repo từ Tier 3-5.
Dùng chung logic với v2 (quét toàn bộ cây thư mục), nhưng GHI NỐI TIẾP vào raw_adrs.json
đã có từ batch 1, không ghi đè.

Cách chạy (sau khi đã chạy xong 1_1_collect_adrs_v2.py):
    python 1_1_collect_adrs_batch2.py

Kết quả: cập nhật raw_adrs.json (nối thêm), collection_log.csv (nối thêm), skipped_files_log.csv
"""
import os
import re
import csv
import json
import time
from github import Github, GithubException

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise SystemExit("Chưa set GITHUB_TOKEN.")

g = Github(GITHUB_TOKEN)

# Ưu tiên repo NHỎ, có tài liệu quyết định tập trung (tránh monorepo khổng lồ dễ bị treo/truncate)
REPOS_BATCH2 = [
    "microservices-patterns/ftgo-application",       # companion sách Chris Richardson, rất có khả năng có decisions doc
    "eventuate-tram/eventuate-tram-core",
    "ContainerSolutions/microservices-patterns",
    "dotnet-architecture/eShopOnContainers",
    "resilience4j/resilience4j",
    "hashicorp/vault",
    "open-policy-agent/opa",
    "jaegertracing/jaeger",
    "cert-manager/cert-manager",
    "crossplane/crossplane",
    "fluxcd/flux2",
    "debezium/debezium",
    "camunda/camunda",
    "kestra-io/kestra",
    "temporalio/temporal",
    "hashicorp/consul",
    "nats-io/nats-server",
    "gitpod-io/gitpod",
    "weaveworks/weave-gitops",
    "Kong/kong",
]

MAX_TREE_ENTRIES = 50000
PATH_KEYWORDS = ["adr", "decision", "rfc", "rationale"]
EXCLUDE_KEYWORDS = ["readme", "template", "index.md", "changelog"]

CONTEXT_PATTERNS = [
    r"##\s*Context(?:\s+and\s+Problem\s+Statement)?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"\*\*Context\*\*\s*\n+(.*?)(?=\n\*\*|\Z)",
    r"##\s*Decision\s+Drivers?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"###\s*Context\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"#\s*Context\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Problem\s+Statement\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Background\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",                 # thêm mới cho batch 2
    r"##\s*Motivation\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",                 # nhiều proposal-style docs dùng "Motivation" thay Context
]
DECISION_PATTERNS = [
    r"##\s*Decision(?:\s+Outcome)?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"\*\*Decision\*\*\s*\n+(.*?)(?=\n\*\*|\Z)",
    r"###\s*Decision\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Chosen\s+Option\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"#\s*Decision\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Proposal\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",                   # thêm mới cho batch 2
    r"##\s*Solution\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
]


def find_adr_files_full_scan(repo):
    found = []
    try:
        default_branch = repo.default_branch
        tree = repo.get_git_tree(sha=default_branch, recursive=True)
    except GithubException as e:
        print(f"    [LỖI TREE] {repo.full_name}: {e}")
        return found

    entries = tree.tree[:MAX_TREE_ENTRIES]
    for item in entries:
        if item.type != "blob":
            continue
        path_lower = item.path.lower()
        if not path_lower.endswith(".md"):
            continue
        if not any(kw in path_lower for kw in PATH_KEYWORDS):
            continue
        if any(kw in path_lower for kw in EXCLUDE_KEYWORDS):
            continue
        found.append({
            "path": item.path,
            "name": item.path.split("/")[-1],
            "url": f"https://github.com/{repo.full_name}/blob/{default_branch}/{item.path}",
        })
    return found


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


def main():
    # nạp dữ liệu cũ để nối tiếp, không ghi đè
    dataset = []
    if os.path.exists("raw_adrs.json"):
        with open("raw_adrs.json", "r", encoding="utf-8") as f:
            dataset = json.load(f)
    existing_urls = {item["url"] for item in dataset}

    log_rows = []
    skipped_rows = []

    for repo_name in REPOS_BATCH2:
        print(f"[SCAN] {repo_name}")
        row = {"repo": repo_name, "md_files_matched": 0,
               "valid_context_decision": 0, "status": "ok"}
        try:
            repo = g.get_repo(repo_name)
            candidate_files = find_adr_files_full_scan(repo)
            row["md_files_matched"] = len(candidate_files)
            print(f"    -> tìm thấy {len(candidate_files)} file .md khả nghi")

            for f in candidate_files:
                if f["url"] in existing_urls:
                    continue
                try:
                    file_content = repo.get_contents(f["path"])
                    content_str = file_content.decoded_content.decode("utf-8", errors="ignore")
                    extracted = extract_context_decision(content_str)

                    if extracted["context"] and len(extracted["context"]) >= 100 and extracted["decision"]:
                        dataset.append({
                            "repo": repo_name,
                            "file": f["name"],
                            "path": f["path"],
                            "url": f["url"],
                            "context": extracted["context"],
                            "decision": extracted["decision"],
                            "context_length": len(extracted["context"]),
                        })
                        row["valid_context_decision"] += 1
                        existing_urls.add(f["url"])
                    else:
                        skipped_rows.append({
                            "repo": repo_name, "path": f["path"],
                            "reason": "context/decision không khớp pattern nào"
                        })
                    time.sleep(0.1)
                except Exception as e:
                    skipped_rows.append({"repo": repo_name, "path": f["path"], "reason": str(e)})

        except GithubException as e:
            row["status"] = f"repo_error: {e}"
            print(f"  [LỖI REPO] {repo_name}: {e}")

        log_rows.append(row)

    with open("raw_adrs.json", "w", encoding="utf-8") as fp:
        json.dump(dataset, fp, ensure_ascii=False, indent=2)

    # nối thêm vào log cũ nếu có, không ghi đè
    write_header = not os.path.exists("collection_log.csv")
    with open("collection_log.csv", "a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["repo", "md_files_matched",
                                                 "valid_context_decision", "status"])
        if write_header:
            writer.writeheader()
        writer.writerows(log_rows)

    write_header2 = not os.path.exists("skipped_files_log.csv")
    with open("skipped_files_log.csv", "a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["repo", "path", "reason"])
        if write_header2:
            writer.writeheader()
        writer.writerows(skipped_rows)

    print("\n=== TÓM TẮT BATCH 2 ===")
    for r in log_rows:
        print(f"{r['repo']:55s} khớp={r['md_files_matched']:4d}  hợp lệ={r['valid_context_decision']:3d}")
    print(f"\nTổng ADR hợp lệ (cả 2 batch cộng dồn): {len(dataset)}")


if __name__ == "__main__":
    main()
