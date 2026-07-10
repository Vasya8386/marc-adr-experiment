"""
2_generation_layer.py
BƯỚC 2 — Generation Layer: gọi 4 model MIỄN PHÍ (Gemini, Groq-Llama, Groq-Gemma2, OpenRouter-DeepSeek-R1)
sinh Decision từ Context, có 2 điều kiện (RAG / không RAG), lặp N lần mỗi tổ hợp.

Yêu cầu cài đặt:
    pip install requests scikit-learn --break-system-packages

Yêu cầu API key (đều lấy MIỄN PHÍ, không cần thẻ):
    - Google AI Studio : https://aistudio.google.com/app/apikey
    - Groq              : https://console.groq.com/keys
    - OpenRouter        : https://openrouter.ai/keys

Set biến môi trường trước khi chạy (cmd):
    set GOOGLE_API_KEY=xxxx
    set GROQ_API_KEY=xxxx
    set OPENROUTER_API_KEY=xxxx

Cách chạy:
    python 2_generation_layer.py

Đặc điểm quan trọng: SCRIPT CÓ CHECKPOINT — nếu bị dừng giữa chừng (rate limit, mất mạng...),
chạy lại lệnh y hệt sẽ tự động BỎ QUA các tổ hợp đã chạy xong, không lặp lại từ đầu.

Kết quả: generation_results.json — mỗi bản ghi là 1 lần sinh (test_id, model, condition, run_index, decision_generated)
"""
import os
import re
import json
import time
import hashlib
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ----------------------------------------------------------------------
# CẤU HÌNH
# ----------------------------------------------------------------------
N_REPEATS = 2          # số lần lặp mỗi tổ hợp (rút gọn cho deadline 2 ngày; tăng lên 5 nếu có thời gian)
TOP_K_RAG = 4           # số ADR gần nhất lấy từ RAG pool
TEMPERATURE = 0.3
MAX_TOKENS = 300

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

MODELS = ["groq-gpt-oss-120b", "groq-gpt-oss-20b", "groq-qwen3.6-27b", "groq-llama-3.1-8b"]
CONDITIONS = ["no_rag", "rag"]

MIN_INTERVAL = {
    "groq-gpt-oss-120b": 1.0,
    "groq-gpt-oss-20b": 1.0,
    "groq-qwen3.6-27b": 1.0,
    "groq-llama-3.1-8b": 1.0,
}

RESULTS_FILE = "generation_results.json"


# ----------------------------------------------------------------------
# GỌI API — 1 hàm thống nhất, bên trong rẽ nhánh theo model
# ----------------------------------------------------------------------
def call_gemini(prompt, model_name="gemini-2.0-flash"):
    if not GOOGLE_API_KEY:
        raise RuntimeError("Chưa set GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GOOGLE_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": MAX_TOKENS},
    }
    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def call_groq(prompt, model_name):
    if not GROQ_API_KEY:
        raise RuntimeError("Chưa set GROQ_API_KEY")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "This is an Architectural Decision Record for a software. "
                                           "Give a ## Decision corresponding to the ## Context provided."},
            {"role": "user", "content": prompt},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    # GPT-OSS là reasoning model -> cần giảm mức suy luận và tăng max_tokens,
    # nếu không phần suy luận nội bộ sẽ chiếm hết token, để lại nội dung trả lời rỗng
    if model_name.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
        body["max_tokens"] = 700
    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def call_openrouter_deepseek(prompt):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Chưa set OPENROUTER_API_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    body = {
        "model": "deepseek/deepseek-r1-0528:free",
        "messages": [
            {"role": "system", "content": "This is an Architectural Decision Record for a software. "
                                           "Give a ## Decision corresponding to the ## Context provided."},
            {"role": "user", "content": prompt},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    r = requests.post(url, headers=headers, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def generate(model, prompt):
    if model == "groq-gpt-oss-120b":
        return call_groq(prompt, "openai/gpt-oss-120b")
    elif model == "groq-gpt-oss-20b":
        return call_groq(prompt, "openai/gpt-oss-20b")
    elif model == "groq-qwen3.6-27b":
        return call_groq(prompt, "qwen/qwen3.6-27b")
    elif model == "groq-llama-3.1-8b":
        return call_groq(prompt, "llama-3.1-8b-instant")
    else:
        raise ValueError(f"Model không xác định: {model}")


# ----------------------------------------------------------------------
# RAG RETRIEVAL — TF-IDF (chạy local, miễn phí, không cần embedding API)
# ----------------------------------------------------------------------
def build_rag_index(rag_pool):
    corpus = [item["context"] for item in rag_pool]
    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english")
    matrix = vectorizer.fit_transform(corpus)
    return vectorizer, matrix


def retrieve_top_k(query_context, vectorizer, matrix, rag_pool, k=TOP_K_RAG):
    query_vec = vectorizer.transform([query_context])
    sims = cosine_similarity(query_vec, matrix)[0]
    top_idx = sims.argsort()[::-1][:k]
    return [rag_pool[i] for i in top_idx]


# ----------------------------------------------------------------------
# PROMPT BUILDER — kế thừa định dạng ## Context / ## Decision từ Dhar et al.
# ----------------------------------------------------------------------
def build_prompt(context, retrieved_examples=None):
    if retrieved_examples:
        knowledge_block = "\n\n".join(
            f"## Related Example\nContext: {ex['context'][:400]}\nDecision: {ex['decision'][:300]}"
            for ex in retrieved_examples
        )
        return f"{knowledge_block}\n\n## Context\n{context}\n\n## Decision\n"
    return f"## Context\n{context}\n\n## Decision\n"


# ----------------------------------------------------------------------
# CHECKPOINT — key duy nhất cho mỗi tổ hợp (test_id, model, condition, run_index)
# ----------------------------------------------------------------------
def make_test_id(item):
    return hashlib.md5(item["url"].encode("utf-8")).hexdigest()[:10]


def load_existing_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def make_combo_key(test_id, model, condition, run_index):
    return f"{test_id}|{model}|{condition}|{run_index}"


def main():
    with open("gold_test_set.json", "r", encoding="utf-8") as f:
        test_set = json.load(f)
    with open("rag_pool.json", "r", encoding="utf-8") as f:
        rag_pool = json.load(f)

    print(f"Test set: {len(test_set)} ADR | RAG pool: {len(rag_pool)} ADR")
    vectorizer, matrix = build_rag_index(rag_pool)

    results = load_existing_results()
    done_keys = {
        make_combo_key(r["test_id"], r["model"], r["condition"], r["run_index"])
        for r in results
    }

    total_combos = len(test_set) * len(MODELS) * len(CONDITIONS) * N_REPEATS
    print(f"Tổng số tổ hợp cần chạy: {total_combos}  (đã có sẵn: {len(done_keys)})")

    count_done_this_run = 0
    count_errors = 0

    for item in test_set:
        test_id = make_test_id(item)
        retrieved = retrieve_top_k(item["context"], vectorizer, matrix, rag_pool)

        for condition in CONDITIONS:
            prompt = build_prompt(item["context"], retrieved if condition == "rag" else None)

            for model in MODELS:
                for run_index in range(1, N_REPEATS + 1):
                    key = make_combo_key(test_id, model, condition, run_index)
                    if key in done_keys:
                        continue

                    try:
                        decision_text = generate(model, prompt)
                        if not decision_text or len(decision_text.strip()) < 10:
                            raise ValueError(f"Output rỗng hoặc quá ngắn ({len(decision_text or '')} ký tự) "
                                              f"-> có thể do reasoning model dùng hết token, không lưu kết quả này")
                        results.append({
                            "test_id": test_id,
                            "repo": item["repo"],
                            "group": item.get("group", "unknown"),
                            "model": model,
                            "condition": condition,
                            "run_index": run_index,
                            "context": item["context"],
                            "actual_decision": item["decision"],
                            "generated_decision": decision_text,
                            "timestamp": time.time(),
                        })
                        done_keys.add(key)
                        count_done_this_run += 1
                        print(f"[OK] {test_id} | {model} | {condition} | run {run_index}")

                        # lưu ngay sau mỗi lần gọi thành công -> mất điện/rớt mạng không mất dữ liệu
                        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                            json.dump(results, f, ensure_ascii=False, indent=2)

                        time.sleep(MIN_INTERVAL.get(model, 2.0))

                    except requests.exceptions.HTTPError as e:
                        status = e.response.status_code if e.response is not None else "?"
                        print(f"[LỖI HTTP {status}] {test_id} | {model} | {condition} | run {run_index}: {e}")
                        count_errors += 1
                        if status == 429:
                            print("    -> Bị rate limit, đợi 30s...")
                            time.sleep(30)
                    except Exception as e:
                        print(f"[LỖI] {test_id} | {model} | {condition} | run {run_index}: {e}")
                        count_errors += 1
                        time.sleep(3)

    print(f"\n=== HOÀN TẤT ===")
    print(f"Đã sinh mới trong lần chạy này: {count_done_this_run}")
    print(f"Lỗi gặp phải: {count_errors}")
    print(f"Tổng kết quả tích lũy trong {RESULTS_FILE}: {len(results)} / {total_combos}")
    if len(results) < total_combos:
        print("Chưa xong toàn bộ -> CHẠY LẠI SCRIPT NÀY (sẽ tự bỏ qua phần đã xong, không chạy lại từ đầu).")


if __name__ == "__main__":
    main()
