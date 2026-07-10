"""
3_evaluation_layer.py
BƯỚC 3 — Evaluation Layer: tính các chỉ số cho cả 4 RQ từ generation_results.json

Yêu cầu cài đặt:
    pip install bert-score scikit-learn pandas --break-system-packages

LƯU Ý QUAN TRỌNG (đọc trước khi chạy):
    - BERTScore cần tải model roberta-large lần đầu chạy (~1.4GB), cần mạng ổn định,
      chỉ tải 1 lần rồi cache lại cho các lần sau.
    - Do giới hạn thời gian, DCR (Decision-Context Relevance) và MCS/DDI được tính bằng
      TF-IDF cosine similarity (tự động, chạy local) THAY VÌ LLM-judge như dự định ban đầu
      trong kiến trúc MARC gốc. Đây là điều chỉnh cần ghi rõ trong Threats to Validity.

Cách chạy:
    python 3_evaluation_layer.py

Kết quả:
    - evaluation_results.json  : mỗi bản ghi gốc + đầy đủ metric (BERTScore, DCR)
    - rq1_summary.csv          : BERTScore trung bình theo model (so sánh với Dhar Table II)
    - rq2_summary.csv          : BERTScore/DCR theo model x điều kiện (RAG/no-RAG) x nhóm G1-G7
    - rq3_summary.csv          : MCS (Multi-run Consistency Score) theo model và theo nhóm
    - rq4_summary.csv          : DDI (Decision-Decision Inter-model Inconsistency) theo nhóm
"""
import json
from collections import defaultdict
from itertools import combinations

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from bert_score import score as bert_score_fn

VALID_MODELS = {"groq-gpt-oss-120b", "groq-gpt-oss-20b", "groq-qwen3.6-27b", "groq-llama-3.1-8b"}

with open("generation_results.json", "r", encoding="utf-8") as f:
    all_results = json.load(f)

# Lọc bỏ các bản ghi Gemini cũ còn sót lại, chỉ giữ đúng 4 model chính thức
results = [r for r in all_results if r["model"] in VALID_MODELS]
print(f"Tổng bản ghi hợp lệ (4 model chính thức): {len(results)} / {len(all_results)} tổng cộng")

# ----------------------------------------------------------------------
# 1. BERTSCORE — so sánh generated_decision với actual_decision
# ----------------------------------------------------------------------
print("\n[1/4] Đang tính BERTScore (lần đầu sẽ tải model ~1.4GB, hãy kiên nhẫn)...")
cands = [r["generated_decision"] for r in results]
refs = [r["actual_decision"] for r in results]
P, R, F1 = bert_score_fn(cands, refs, lang="en", verbose=True)

for i, r in enumerate(results):
    r["bertscore_precision"] = float(P[i])
    r["bertscore_recall"] = float(R[i])
    r["bertscore_f1"] = float(F1[i])

# ----------------------------------------------------------------------
# 2. DCR (Decision-Context Relevance) — TF-IDF cosine(context, generated_decision)
#    Thay thế LLM-judge do giới hạn thời gian -> cần ghi rõ trong Threats to Validity
# ----------------------------------------------------------------------
print("\n[2/4] Đang tính DCR (TF-IDF cosine similarity Context-Decision)...")
all_texts = [r["context"] for r in results] + [r["generated_decision"] for r in results]
vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
matrix = vectorizer.fit_transform(all_texts)
n = len(results)
context_vecs = matrix[:n]
decision_vecs = matrix[n:]
for i, r in enumerate(results):
    sim = cosine_similarity(context_vecs[i], decision_vecs[i])[0][0]
    r["dcr"] = float(sim)

# ----------------------------------------------------------------------
# 3. MCS (Multi-run Consistency Score) — cosine similarity giữa các lần lặp
#    của CÙNG (test_id, model, condition)
# ----------------------------------------------------------------------
print("\n[3/4] Đang tính MCS (đồng nhất qua nhiều lần lặp)...")
groups_for_mcs = defaultdict(list)
for r in results:
    key = (r["test_id"], r["model"], r["condition"])
    groups_for_mcs[key].append(r)

mcs_records = []
decision_vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
all_decisions_corpus = [r["generated_decision"] for r in results]
decision_vectorizer.fit(all_decisions_corpus)

for (test_id, model, condition), records in groups_for_mcs.items():
    if len(records) < 2:
        continue
    texts = [rec["generated_decision"] for rec in records]
    vecs = decision_vectorizer.transform(texts)
    sims = []
    for i, j in combinations(range(len(texts)), 2):
        sims.append(cosine_similarity(vecs[i], vecs[j])[0][0])
    mcs = sum(sims) / len(sims)
    mcs_records.append({
        "test_id": test_id, "model": model, "condition": condition,
        "group": records[0]["group"], "mcs": mcs, "n_runs": len(records),
    })
    for rec in records:
        rec["mcs"] = mcs

# ----------------------------------------------------------------------
# 4. DDI (Decision-Decision Inter-model Inconsistency)
#    So sánh Decision giữa CÁC MODEL KHÁC NHAU cho cùng (test_id, condition, run_index)
# ----------------------------------------------------------------------
print("\n[4/4] Đang tính DDI (bất đồng giữa các model)...")
groups_for_ddi = defaultdict(list)
for r in results:
    key = (r["test_id"], r["condition"], r["run_index"])
    groups_for_ddi[key].append(r)

ddi_records = []
for (test_id, condition, run_index), records in groups_for_ddi.items():
    if len(records) < 2:
        continue
    texts = [rec["generated_decision"] for rec in records]
    vecs = decision_vectorizer.transform(texts)
    sims = []
    for i, j in combinations(range(len(texts)), 2):
        sims.append(cosine_similarity(vecs[i], vecs[j])[0][0])
    mean_sim = sum(sims) / len(sims)
    ddi = 1 - mean_sim
    ddi_records.append({
        "test_id": test_id, "condition": condition, "run_index": run_index,
        "group": records[0]["group"], "ddi": ddi, "n_models": len(records),
    })

# ----------------------------------------------------------------------
# LƯU KẾT QUẢ CHI TIẾT
# ----------------------------------------------------------------------
with open("evaluation_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

df = pd.DataFrame(results)

# ---- RQ1: BERTScore trung bình theo model (so với Dhar Table II) ----
rq1 = df.groupby("model")[["bertscore_precision", "bertscore_recall", "bertscore_f1"]].mean().reset_index()
rq1.to_csv("rq1_summary.csv", index=False)

# ---- RQ2: BERTScore + DCR theo model x điều kiện x nhóm ----
rq2 = df.groupby(["model", "condition", "group"])[["bertscore_f1", "dcr"]].mean().reset_index()
rq2.to_csv("rq2_summary.csv", index=False)

# ---- RQ3: MCS theo model và theo nhóm ----
mcs_df = pd.DataFrame(mcs_records)
rq3_by_model = mcs_df.groupby("model")["mcs"].mean().reset_index()
rq3_by_group = mcs_df.groupby("group")["mcs"].mean().reset_index()
with open("rq3_summary.csv", "w", encoding="utf-8") as f:
    f.write("=== MCS theo model ===\n")
    rq3_by_model.to_csv(f, index=False)
    f.write("\n=== MCS theo nhóm G1-G7 ===\n")
    rq3_by_group.to_csv(f, index=False)

# ---- RQ4: DDI theo nhóm và điều kiện ----
ddi_df = pd.DataFrame(ddi_records)
rq4 = ddi_df.groupby(["condition", "group"])["ddi"].mean().reset_index()
rq4.to_csv("rq4_summary.csv", index=False)

print("\n=== HOÀN TẤT BƯỚC 3 ===")
print("\n--- RQ1: BERTScore trung bình theo model ---")
print(rq1.to_string(index=False))
print("\n--- RQ3: MCS trung bình theo model ---")
print(rq3_by_model.to_string(index=False))
print("\n--- RQ4: DDI trung bình theo điều kiện ---")
print(ddi_df.groupby("condition")["ddi"].mean().to_string())
print("\nĐã lưu: evaluation_results.json, rq1_summary.csv, rq2_summary.csv, rq3_summary.csv, rq4_summary.csv")
