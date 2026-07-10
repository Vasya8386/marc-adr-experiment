"""
1_1_collect_adrs_v2.py
BƯỚC 1.1 (PHIÊN BẢN 2) — Quét TOÀN BỘ cây thư mục của repo thay vì đoán tên thư mục cố định.
Lý do đổi: v1 chỉ dò các thư mục có sẵn trong danh sách (docs/adr, doc/adr...) nên bị miss
rất nhiều repo đặt tên khác (ví dụ "examples/", ADR để ngay ở gốc repo, v.v.)

Yêu cầu:
    pip install requests PyGithub --break-system-packages
    set GITHUB_TOKEN=token_cua_ban   (cmd)   hoặc   $env:GITHUB_TOKEN="..."  (PowerShell)

Cách chạy:
    python 1_1_collect_adrs_v2.py

Kết quả:
    - raw_adrs.json
    - collection_log.csv
    - skipped_files_log.csv   (MỚI: liệt kê file tìm thấy nhưng KHÔNG trích được context/decision,
                                 để bạn biết cần thêm pattern regex nào)
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

REPOS = [
    "implementing-microservices/ADRs",
    "opinionated-digital-center/architecture-decision-records",
    "AlexTsvetkov/architecture-decision-records",
    "adr/gadr",
    "joelparkerhenderson/architecture-decision-record",
    "eclipse/winery",
    "arachne-framework/architecture",
    "input-output-hk/cardano-node",
    "island-is/island.is",
    "backstage/backstage",
    "knative/serving",
    "dapr/dapr",
    "open-telemetry/opentelemetry-specification",
    "argoproj/argo-cd",
    "tektoncd/pipeline",
]

# Từ khóa nhận diện file/thư mục có khả năng là ADR — quét toàn bộ path, không giới hạn tên thư mục cố định
PATH_KEYWORDS = ["adr", "decision", "rfc", "rationale"]
EXCLUDE_KEYWORDS = ["readme", "template", "index.md", "changelog"]

# Giới hạn quét cho repo lớn (monorepo như backstage, island.is, kubernetes...) để không tốn quota
MAX_TREE_ENTRIES = 50000


def find_adr_files_full_scan(repo):
    """Dùng Git Tree API (1 lệnh gọi duy nhất) để lấy toàn bộ đường dẫn file trong repo,
    sau đó lọc theo từ khóa. Nhanh và đầy đủ hơn nhiều so với việc dò từng thư mục."""
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


CONTEXT_PATTERNS = [
    r"##\s*Context(?:\s+and\s+Problem\s+Statement)?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"\*\*Context\*\*\s*\n+(.*?)(?=\n\*\*|\Z)",
    r"##\s*Decision\s+Drivers?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"###\s*Context\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"#\s*Context\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",                      # heading cấp 1
    r"##\s*Problem\s+Statement\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",          # một số ADR dùng tên này
]
DECISION_PATTERNS = [
    r"##\s*Decision(?:\s+Outcome)?\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"\*\*Decision\*\*\s*\n+(.*?)(?=\n\*\*|\Z)",
    r"###\s*Decision\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"##\s*Chosen\s+Option\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
    r"#\s*Decision\s*\n+(.*?)(?=\n#{1,3}\s|\Z)",
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


def main():
    dataset = []
    log_rows = []
    skipped_rows = []

    for repo_name in REPOS:
        print(f"[SCAN] {repo_name}")
        row = {"repo": repo_name, "md_files_matched": 0,
               "valid_context_decision": 0, "status": "ok"}
        try:
            repo = g.get_repo(repo_name)
            candidate_files = find_adr_files_full_scan(repo)
            row["md_files_matched"] = len(candidate_files)
            print(f"    -> tìm thấy {len(candidate_files)} file .md khả nghi")

            for f in candidate_files:
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

    with open("collection_log.csv", "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["repo", "md_files_matched",
                                                 "valid_context_decision", "status"])
        writer.writeheader()
        writer.writerows(log_rows)

    with open("skipped_files_log.csv", "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["repo", "path", "reason"])
        writer.writeheader()
        writer.writerows(skipped_rows)

    print("\n=== TÓM TẮT ===")
    for r in log_rows:
        flag = "  << ÍT, CÂN NHẮC BỎ" if r["valid_context_decision"] < 3 else ""
        print(f"{r['repo']:55s} khớp={r['md_files_matched']:4d}  hợp lệ={r['valid_context_decision']:3d}{flag}")
    print(f"\nTổng ADR hợp lệ: {len(dataset)}")
    print(f"Số file bị bỏ qua (không khớp pattern): {len(skipped_rows)} -> xem skipped_files_log.csv")
    print("Đã lưu: raw_adrs.json, collection_log.csv, skipped_files_log.csv")


if __name__ == "__main__":
    main()
