# MARC — Pipeline Thực Nghiệm Sinh ADR bằng LLM

Hướng dẫn đầy đủ để chạy lại toàn bộ pipeline: thu thập dữ liệu → sinh Decision bằng 4 LLM → tính điểm đánh giá. Mỗi bước dưới đây đều giải thích rõ **file đó làm gì, lệnh chạy nó làm gì, và kết quả thu về là gì** — để bất kỳ ai trong nhóm cũng có thể tự chạy mà không cần hỏi lại.

---

## 0. Yêu cầu trước khi bắt đầu

- Python 3.10 trở lên
- Git
- Tài khoản GitHub (để lấy Personal Access Token)
- Tài khoản Groq (miễn phí, để lấy API key)

### Cài đặt thư viện

```bash
git clone <https://github.com/Vasya8386/marc-adr-experiment>
cd marc-adr-experiment
pip install -r requirements.txt
```

**Lệnh này làm gì:** tải toàn bộ code của nhóm về máy, sau đó cài đặt tất cả thư viện Python mà các script cần để chạy (danh sách nằm trong `requirements.txt` — gồm `requests`/`PyGithub` để gọi GitHub API, `scikit-learn`/`pandas` để xử lý dữ liệu, `bert-score` để tính điểm chất lượng).

**Kết quả thu về:** một thư mục `marc-adr-experiment/` trên máy bạn chứa toàn bộ code, và các thư viện cần thiết đã sẵn sàng dùng được trong Python.

Nếu pip báo lỗi "externally-managed-environment" (thường gặp trên Linux/Mac), thêm `--break-system-packages` vào cuối lệnh `pip install`.

---

## 1. Lấy API Key (bắt buộc trước khi chạy bất kỳ script nào)

### 1.1. GitHub Personal Access Token

**Dùng để làm gì:** tất cả script thu thập dữ liệu (Bước 2 bên dưới) đều gọi đến GitHub API để tìm và tải ADR từ các repository công khai. GitHub giới hạn số lượt gọi API rất thấp (60 lượt/giờ) nếu không có token, nhưng cho phép tới 5000 lượt/giờ nếu có token — vì vậy bắt buộc phải có token thì script mới chạy đủ nhanh và đủ nhiều.

**Cách lấy:**
1. Vào https://github.com/settings/tokens
2. Bấm **Generate new token** → chọn **Fine-grained tokens**
3. Đặt tên bất kỳ, ví dụ `marc-adr-collector`
4. **Expiration**: chọn 30-90 ngày là đủ dùng cho cả đợt làm thực nghiệm
5. **Repository access**: chọn **Public repositories (read-only)** — không cần cấp quyền ghi vì mình chỉ đọc dữ liệu
6. Bấm **Generate token** ở cuối trang

**Kết quả thu về:** một chuỗi ký tự dạng `github_pat_xxxxxxxxxx`. **GitHub chỉ hiện chuỗi này đúng 1 lần** — copy lại ngay, đóng trang là mất vĩnh viễn (phải tạo token mới nếu quên copy).

### 1.2. Groq API Key

**Dùng để làm gì:** dùng ở Bước 4 (sinh Decision) — đây là API key để gọi 4 model LLM (GPT-OSS-120B, GPT-OSS-20B, Qwen3.6-27B, Llama-3.1-8B) đang được host miễn phí trên nền tảng Groq.

**Cách lấy:**
1. Vào https://console.groq.com/keys
2. Đăng nhập hoặc đăng ký tài khoản (miễn phí hoàn toàn, không cần nhập thẻ)
3. Bấm **Create API Key**

**Kết quả thu về:** một chuỗi ký tự dạng `gsk_xxxxxxxxxx` — copy lại ngay vì cũng chỉ hiện 1 lần.

### 1.3. Set biến môi trường

**Việc này để làm gì:** các script không ghi API key trực tiếp trong code (để tránh lộ key khi đưa code lên GitHub công khai) — thay vào đó, script đọc key từ "biến môi trường" của hệ điều hành. Bạn cần khai báo 2 biến này trước khi chạy bất kỳ script nào cần đến chúng.

** Không bao giờ dán API key trực tiếp vào code hoặc gửi qua chat/tin nhắn công khai.**

**Windows (Command Prompt) — gõ trong cửa sổ cmd:**
```cmd
set GITHUB_TOKEN=github_pat_xxxxxxxxxx
set GROQ_API_KEY=gsk_xxxxxxxxxx
```

**Windows (PowerShell):**
```powershell
$env:GITHUB_TOKEN="github_pat_xxxxxxxxxx"
$env:GROQ_API_KEY="gsk_xxxxxxxxxx"
```

**Linux / Mac:**
```bash
export GITHUB_TOKEN="github_pat_xxxxxxxxxx"
export GROQ_API_KEY="gsk_xxxxxxxxxx"
```

**Kết quả sau khi chạy 2 lệnh trên:** không có gì hiện ra trên màn hình (bình thường) — nhưng từ giờ, mọi script Python chạy trong **cùng cửa sổ terminal này** sẽ tự đọc được 2 giá trị đó thông qua `os.environ.get("GITHUB_TOKEN")` trong code.

**Lưu ý quan trọng:** biến môi trường chỉ tồn tại trong đúng cửa sổ terminal đang mở — đóng terminal thì phải gõ lại lệnh `set`/`export` từ đầu. Kiểm tra đã set đúng chưa bằng lệnh `echo %GITHUB_TOKEN%` (cmd) hoặc `echo $GITHUB_TOKEN` (Linux/Mac/PowerShell dùng `echo $env:GITHUB_TOKEN`) — nếu hiện đúng chuỗi key thì đã set thành công.

---

## 2. Thu thập dữ liệu (Bước 1) — giải thích từng file rồi mới chạy

### Vì sao cần nhiều file thay vì 1 file duy nhất?

Quá trình thu thập dữ liệu của nhóm trải qua nhiều lần thử-sai để tìm ra cách hiệu quả nhất, và mỗi file dưới đây tương ứng với 1 giai đoạn cải tiến — chạy đúng thứ tự để hiểu được logic, và vì các file sau phụ thuộc vào dữ liệu do file trước tạo ra (đọc và nối thêm, không ghi đè).

### `1_1_collect_adrs_v2.py`

**File này làm gì:** cầm theo một danh sách 15 repository GitHub được chọn sẵn (những dự án lớn, khả năng cao có tài liệu ADR — ví dụ Backstage, Dapr, Winery). Với mỗi repo, thay vì đoán tên thư mục chứa ADR, script dùng **GitHub Git Tree API** để lấy toàn bộ danh sách đường dẫn file trong repo đó chỉ bằng 1 lệnh gọi duy nhất, rồi tự lọc ra những file `.md` có chứa từ khóa `adr`, `decision`, `rfc`, hoặc `rationale` trong đường dẫn — bất kể file nằm ở thư mục nào trong repo. Với mỗi file tìm được, script tải nội dung về và dùng biểu thức chính quy (regex) để tách riêng phần Context và phần Decision.

**Lệnh chạy:**
```bash
python 1_1_collect_adrs_v2.py
```

**Kết quả thu về:**
- `raw_adrs.json` — danh sách các ADR đã trích xuất được (mỗi ADR gồm: repo nguồn, đường dẫn file, nội dung Context, nội dung Decision)
- `collection_log.csv` — bảng thống kê cho biết mỗi repo tìm được bao nhiêu file khớp từ khóa, và trích xuất thành công được bao nhiêu ADR hợp lệ (để biết repo nào nên bỏ vì cho quá ít kết quả)
- `skipped_files_log.csv` — liệt kê những file tìm thấy nhưng không trích xuất được Context/Decision (dùng để biết cần bổ sung mẫu regex nào)

### `1_1_collect_adrs_batch2.py`

**File này làm gì:** chạy sau file trên, **đọc lại** `raw_adrs.json` đã có và nối thêm dữ liệu mới vào cuối (không xóa dữ liệu cũ). Nó quét tiếp 20 repository khác (các dự án nhỏ hơn nhưng có khả năng chứa ADR về microservices), đồng thời bổ sung thêm 2 mẫu regex mới để nhận diện các ADR viết theo kiểu khác (dùng tiêu đề `## Background` hoặc `## Motivation` thay cho `## Context`).

**Lệnh chạy:**
```bash
python 1_1_collect_adrs_batch2.py
```

**Kết quả thu về:** `raw_adrs.json` được cập nhật (số lượng ADR tăng lên so với trước khi chạy file này).

### `1_1_collect_adrs_batch3.py`

**File này làm gì:** tương tự batch2 nhưng quét thêm 15 repository nữa (bao gồm một số dự án lớn hơn). Điểm khác biệt: file này có logic **tự động dừng lại ngay khi tổng số ADR đạt 120** — không cần quét hết toàn bộ danh sách nếu đã đủ số lượng cần thiết, giúp tiết kiệm thời gian.

**Lệnh chạy:**
```bash
python 1_1_collect_adrs_batch3.py
```

**Kết quả thu về:** `raw_adrs.json` cập nhật thêm, dừng khi đạt 120 ADR hoặc hết danh sách repo.

### `1_1_collect_adrs_batch4_discovery.py` — file quan trọng nhất

**File này làm gì:** ba file phía trên đều dựa trên việc **đoán tên repository trước rồi mới quét** — cách này có giới hạn cố hữu vì không thể biết hết mọi repo có ADR trên GitHub. File này đổi hẳn chiến thuật: dùng **GitHub Code Search API** để hỏi thẳng GitHub "tìm giúp tôi mọi file trên toàn bộ GitHub công khai có nội dung giống ADR" — ví dụ tìm những file có cả `## Context` và `## Decision` xuất hiện cùng lúc, hoặc có cụm từ "Considered Options". GitHub trả về những file thật sự khớp, script tải về và tự trích xuất y như các bước trước.

**Lệnh chạy:**
```bash
python 1_1_collect_adrs_batch4_discovery.py
```

**Kết quả thu về:** `raw_adrs.json` cập nhật (tăng nhanh nhất trong tất cả các bước — trong lần chạy thực tế của nhóm, bước này tự phát hiện ra 44 repository hoàn toàn mới mà không ai trong nhóm biết trước), và file `discovered_repos.txt` liệt kê tên các repo mới được tìm thấy.

**Lưu ý khi chạy:** GitHub Code Search API giới hạn khá chặt (~10 lượt gọi/phút), nên script này chạy chậm hơn các file trước (có nghỉ giữa các lượt gọi) — có thể mất 10-15 phút, cứ để chạy, đừng ngắt giữa chừng.

### `1_3_label_groups.py`

**File này làm gì:** không thu thập thêm dữ liệu mà **gán nhãn** — xếp mỗi ADR trong `raw_adrs.json` vào 1 trong 7 nhóm chủ đề microservices (G1 Service Decomposition, G2 Communication, G3 Data Management, G4 API Gateway/Discovery, G5 Deployment/Orchestration, G6 Resilience, G7 Observability/Security). Cách hoạt động: script tự chấm điểm mỗi ADR dựa trên từ khóa xuất hiện trong nội dung (ví dụ thấy chữ "circuit breaker" thì điểm nghiêng về nhóm Resilience), rồi hiển thị lên màn hình: nội dung Context/Decision thật của ADR đó, kèm theo nhóm mà script đề xuất. Bạn chỉ cần:
- Bấm **Enter** nếu đồng ý với đề xuất
- Gõ số **1-7** nếu muốn chọn nhóm khác
- Gõ **s** để bỏ qua ADR đó (không thuộc nhóm nào rõ ràng)
- Gõ **q** để dừng và lưu lại, có thể chạy lại sau để tiếp tục đúng chỗ đã dừng

**Lệnh chạy:**
```bash
python 1_3_label_groups.py
```

**Kết quả thu về:** `labeled_adrs.json` — mỗi ADR giờ có thêm trường `group` cho biết thuộc nhóm nào. Cuối quá trình, màn hình in ra bảng thống kê số lượng ADR mỗi nhóm, kèm cảnh báo nhóm nào đang có dưới 15 ADR (nhóm đó cần bổ sung thêm ở bước tiếp theo).

### `1_1_collect_adrs_batch5_targeted.py`

**File này làm gì:** chỉ cần chạy nếu bước trên báo có nhóm nào đó quá ít ADR (dưới 15). File này tìm kiếm **có chủ đích**, chỉ nhắm vào từ khóa đặc trưng của đúng nhóm đang thiếu (mặc định cấu hình sẵn cho G4 API Gateway và G6 Resilience — sửa biến `SEARCH_QUERIES` trong file nếu nhóm khác đang thiếu). Có thêm bước lọc kép để đảm bảo kết quả tìm được thực sự thuộc đúng nhóm cần bổ sung, tránh vô tình làm phình to thêm các nhóm vốn đã dư thừa.

**Lệnh chạy:**
```bash
python 1_1_collect_adrs_batch5_targeted.py
```

**Kết quả thu về:** `labeled_adrs.json` cập nhật thêm ADR cho đúng (các) nhóm đang thiếu, kèm bảng thống kê phân bố mới in ra màn hình.

### `1_2_manual_check_sample.py`

**File này làm gì:** đây là bước kiểm tra chất lượng, không bắt buộc nhưng nên làm. Nó lấy ngẫu nhiên 10% số ADR đã có, xuất ra một file riêng để bạn tự đọc bằng mắt — mục đích là phát hiện xem regex trích xuất có cắt nhầm giữa câu, hay lẫn nội dung của mục khác (như "Status", "Consequences") vào phần Context/Decision hay không.

**Lệnh chạy:**
```bash
python 1_2_manual_check_sample.py
```

**Kết quả thu về:** `sample_to_review.json` — mở file này lên, đọc từng mẫu, tự đánh giá xem trích xuất có đúng không. Nếu phát hiện nhiều lỗi, quay lại sửa mẫu regex trong các file batch ở trên rồi chạy lại từ đầu.

### `1_4_split_dataset.py`

**File này làm gì:** đây là file cuối cùng của Bước 1 — chia toàn bộ ADR đã gán nhãn thành 2 phần riêng biệt:
- **Test set (bộ kiểm tra)**: 18 ADR, ưu tiên chọn những ADR có mục "Considered Options" (vì chúng đầy đủ thông tin hơn để đánh giá), dùng để cho 4 model LLM sinh Decision và so sánh kết quả ở các bước sau.
- **RAG pool (kho tham chiếu)**: toàn bộ ADR còn lại, dùng để LLM tra cứu ví dụ tương tự khi bật chế độ RAG (Retrieval-Augmented Generation).

Quan trọng nhất: script **tự động kiểm tra chéo** để đảm bảo không có ADR nào vừa nằm trong test set vừa nằm trong RAG pool — nếu để lẫn, khi làm bài kiểm tra, RAG sẽ vô tình "nhìn thấy đáp án" của chính câu hỏi đang được hỏi, làm sai lệch toàn bộ kết quả đánh giá (hiện tượng gọi là rò rỉ dữ liệu — data leakage).

**Lệnh chạy:**
```bash
python 1_4_split_dataset.py
```

**Kết quả thu về:**
- `gold_test_set.json` — 18 ADR dùng để đánh giá
- `rag_pool.json` — phần còn lại dùng làm kho tham chiếu
- `split_summary.csv` — thống kê phân bố 7 nhóm ở mỗi tập, để kiểm tra tính cân bằng
- Dòng chữ `[OK] Không có rò rỉ dữ liệu` in ra màn hình nếu kiểm tra chéo thành công

### Tiêu chí để biết Bước 1 đã hoàn thành

- Tổng số ADR ≥ 120
- Mỗi nhóm G1-G7 lý tưởng ≥ 15 (một số nhóm hiếm gặp thực tế như Resilience có thể thấp hơn — đây là hạn chế thật của dữ liệu công khai, không phải lỗi kỹ thuật, cần ghi rõ vào phần Threats to Validity của bài báo)
- `split_summary.csv` không báo cảnh báo rò rỉ dữ liệu

---

## 3. Kiểm tra model Groq còn hoạt động — chạy trước Bước 4

### `check_groq_models.py`

**File này làm gì và vì sao cần có nó:** Groq thường xuyên thay đổi danh mục model được hỗ trợ — có những model nhóm đã dùng thành công bị Groq ngừng hỗ trợ chỉ vài tuần sau đó (nhóm đã gặp thực tế với `llama-3.3-70b-versatile`, `llama-4-maverick`, `gemma2-9b-it`). File này gọi thẳng đến API của Groq để lấy **danh sách model đang thực sự hoạt động tại thời điểm bạn chạy**, thay vì tin vào tên model được viết cứng trong tài liệu hay code cũ.

**Lệnh chạy:**
```bash
python check_groq_models.py
```

**Kết quả thu về:** một bảng in ra màn hình liệt kê mọi model đang khả dụng trên tài khoản Groq của bạn, kèm tên nhà phát triển gốc (OpenAI, Meta, Alibaba...). Đối chiếu bảng này với tên model đang khai báo trong biến `MODELS` và hàm `generate()` của file `2_generation_layer.py` — nếu có model nào trong code không còn xuất hiện ở đây, cần sửa lại tên model trong `2_generation_layer.py` trước khi chạy Bước 4.

---

## 4. Sinh Decision bằng 4 LLM (Bước 2 trong framework — file `2_`)

### `2_generation_layer.py`

**File này làm gì:** đây là bước cốt lõi của toàn bộ thực nghiệm. Với mỗi ADR trong `gold_test_set.json`, script:
1. Xây dựng prompt theo định dạng chuẩn (`## Context` / `## Decision`, kế thừa từ Dhar et al. 2024)
2. Nếu ở điều kiện có RAG: tìm 4 ADR giống nhất trong `rag_pool.json` (dùng TF-IDF cosine similarity) và chèn vào prompt làm ví dụ tham khảo
3. Gửi prompt đó tới cả 4 model (GPT-OSS-120B, GPT-OSS-20B, Qwen3.6-27B, Llama-3.1-8B) qua Groq API
4. Lặp lại mỗi tổ hợp (ADR × model × điều kiện) đúng 2 lần để sau này đo được tính nhất quán

**Lệnh chạy:**
```bash
python 2_generation_layer.py
```

**Kết quả thu về:** `generation_results.json` — mỗi bản ghi trong file này là kết quả của đúng 1 lượt sinh, gồm: ADR nào, model nào, điều kiện nào (có RAG hay không), lần lặp thứ mấy, và nội dung Decision mà model đó sinh ra.

**Đặc điểm quan trọng — có checkpoint tự động:** mỗi lần gọi API thành công được lưu vào file kết quả ngay lập tức. Nếu quá trình bị gián đoạn (mất mạng, rate limit, Ctrl+C giữa chừng), chỉ cần **chạy lại đúng lệnh này** — script sẽ tự nhận diện những tổ hợp đã hoàn thành và bỏ qua, không tốn lại API call đã dùng.

**Các lỗi thường gặp và cách xử lý:**
- **Lỗi 404 liên tục cho 1 model cụ thể:** tên model đó đã bị Groq ngừng hỗ trợ → chạy lại `check_groq_models.py`, cập nhật tên model đúng trong code
- **Lỗi 429 xuất hiện ở MỌI lượt gọi không sót cái nào:** đây là hết hạn ngạch theo ngày, không phải do gọi quá nhanh → đợi hạn ngạch reset (thường vào nửa đêm theo múi giờ của nhà cung cấp) hoặc dùng API key khác
- **Cảnh báo "Empty candidate sentence" xuất hiện ở Bước 5 (đánh giá):** một số model dạng "reasoning" (như GPT-OSS) có thể dùng hết token cho bước suy nghĩ nội bộ, không còn token để viết câu trả lời thật. Nếu gặp lại dù code đã có sẵn cấu hình xử lý việc này, chạy 2 lệnh sau:
  ```bash
  python 2b_cleanup_empty_results.py
  python 2_generation_layer.py
  ```
  (lệnh đầu xóa các bản ghi có nội dung rỗng khỏi `generation_results.json`, lệnh sau sẽ tự động sinh lại đúng những tổ hợp vừa bị xóa)

### `2b_cleanup_empty_results.py`

**File này làm gì:** đọc `generation_results.json`, tìm và xóa các bản ghi có nội dung Decision bị rỗng hoặc quá ngắn (dưới 10 ký tự — dấu hiệu của lỗi reasoning model nêu trên), rồi lưu lại file đã dọn sạch.

**Lệnh chạy:**
```bash
python 2b_cleanup_empty_results.py
```

**Kết quả thu về:** `generation_results.json` được ghi đè bằng phiên bản đã loại bỏ các bản ghi lỗi, kèm dòng thông báo "đã xóa bao nhiêu bản ghi" in ra màn hình. Chạy xong, chạy lại `2_generation_layer.py` để tự động sinh lại đúng phần vừa bị xóa.

---

## 5. Tính điểm đánh giá (Bước 3 — Evaluation Layer)

### `3_evaluation_layer.py`

**File này làm gì:** đọc toàn bộ `generation_results.json`, và với mỗi bản ghi, tính ra 4 chỉ số:
- **BERTScore** (Precision/Recall/F1) — so sánh Decision do model sinh ra với Decision thật trong ADR gốc, dùng model ngôn ngữ BERT để đo độ giống nhau về mặt ngữ nghĩa (không chỉ trùng từ)
- **DCR (Decision-Context Relevance)** — đo Decision sinh ra có bám sát đúng Context được hỏi hay không, bằng cách tính độ tương đồng cosine giữa 2 đoạn văn bản (dùng TF-IDF)
- **MCS (Multi-run Consistency Score)** — với mỗi tổ hợp (ADR, model, điều kiện) có 2 lần lặp, tính độ giống nhau giữa 2 lần sinh đó — càng cao nghĩa là model càng nhất quán khi được hỏi lại
- **DDI (Decision-Decision inter-model Inconsistency)** — với mỗi (ADR, điều kiện, lần lặp), so sánh Decision của 4 model khác nhau với nhau — càng cao nghĩa là 4 model càng bất đồng

Sau khi tính xong từng bản ghi, script tổng hợp lại thành các bảng trung bình theo model, theo nhóm chủ đề, theo điều kiện RAG/không RAG — tương ứng trực tiếp với 4 câu hỏi nghiên cứu (RQ1-RQ4) của bài báo.

**Lệnh chạy:**
```bash
python 3_evaluation_layer.py
```

**Kết quả thu về:**
| File | Nội dung cụ thể |
|---|---|
| `evaluation_results.json` | Toàn bộ dữ liệu gốc từ Bước 4, cộng thêm 4 cột điểm số (BERTScore, DCR) cho từng bản ghi |
| `rq1_summary.csv` | Điểm BERTScore trung bình của mỗi model — dùng để so sánh trực tiếp với baseline GPT-4 (0.849) trong bài của Dhar et al. |
| `rq2_summary.csv` | Điểm BERTScore và DCR trung bình, tách theo từng model × điều kiện (RAG/không RAG) × nhóm chủ đề — cho biết RAG có ích ở loại quyết định nào |
| `rq3_summary.csv` | Điểm MCS trung bình theo model và theo nhóm chủ đề — bảng quan trọng nhất, trả lời câu hỏi "model nào nhất quán nhất" |
| `rq4_summary.csv` | Điểm DDI trung bình theo nhóm và theo điều kiện — cho biết các model có đồng thuận với nhau nhiều hơn khi có RAG hay không |

**Lưu ý khi chạy:** không cần API key nào ở bước này — mọi thứ chạy hoàn toàn trên máy bạn (local). Lần đầu chạy, thư viện `bert-score` sẽ tự động tải một model ngôn ngữ (roberta-large, khoảng 1.4GB) về máy — cần mạng ổn định, và chỉ tải 1 lần duy nhất cho các lần chạy sau. Với khoảng 290 bản ghi, việc tính điểm trên CPU (không có GPU riêng) có thể mất 5-15 phút — cứ để chạy, không cần can thiệp.

---

## 6. Toàn bộ pipeline tóm tắt — copy-paste chạy liền mạch

```bash
# Cài đặt thư viện
pip install -r requirements.txt

# Set API key (thay bằng giá trị thật của bạn)
export GITHUB_TOKEN="github_pat_..."
export GROQ_API_KEY="gsk_..."

# Bước 1: Thu thập dữ liệu (chạy đúng thứ tự, mỗi lệnh nối thêm dữ liệu vào lệnh trước)
python 1_1_collect_adrs_v2.py
python 1_1_collect_adrs_batch2.py
python 1_1_collect_adrs_batch3.py
python 1_1_collect_adrs_batch4_discovery.py
python 1_3_label_groups.py
python 1_1_collect_adrs_batch5_targeted.py   # chỉ chạy nếu bước trên báo còn nhóm thiếu
python 1_4_split_dataset.py

# Bước 2: Kiểm tra model Groq còn sống trước, rồi mới sinh dữ liệu
python check_groq_models.py                  # đối chiếu tên model với 2_generation_layer.py trước khi chạy dòng dưới
python 2_generation_layer.py

# Bước 3: Tính điểm đánh giá
python 3_evaluation_layer.py
```

---

## 7. Cấu trúc thư mục

```
marc-adr-experiment/
├── README.md
├── requirements.txt
├── .gitignore
├── 1_1_collect_adrs_v2.py                    # Thu thập: 15 repo chọn sẵn, quét toàn bộ cây thư mục
├── 1_1_collect_adrs_batch2.py                # Thu thập: thêm 20 repo Tier 3
├── 1_1_collect_adrs_batch3.py                # Thu thập: thêm 15 repo, tự dừng ở 120 ADR
├── 1_1_collect_adrs_batch4_discovery.py      # Thu thập: GitHub Code Search (quan trọng nhất)
├── 1_1_collect_adrs_batch5_targeted.py       # Thu thập: bổ sung riêng cho nhóm còn thiếu
├── 1_2_manual_check_sample.py                # Kiểm tra chất lượng trích xuất (thủ công)
├── 1_3_label_groups.py                       # Gán nhãn 7 nhóm chủ đề
├── 1_4_split_dataset.py                      # Tách test set / RAG pool
├── check_groq_models.py                      # Kiểm tra model Groq còn hoạt động
├── 2_generation_layer.py                     # Sinh Decision bằng 4 LLM
├── 2b_cleanup_empty_results.py               # Dọn kết quả sinh bị rỗng
└── 3_evaluation_layer.py                     # Tính BERTScore, DCR, MCS, DDI
```

Tất cả file dữ liệu (`.json`, `.csv`) được các script tự động tạo ra khi chạy, nằm cùng thư mục với code — không cần tạo tay trước khi chạy.

---

## 8. Lưu ý bảo mật — đọc trước khi push code lên GitHub

- **Không bao giờ commit file chứa API key thật.** File `.env` đã nằm sẵn trong `.gitignore` để tránh bị commit nhầm.
- Nếu ai đó trong nhóm lỡ dán API key vào code rồi commit/push lên GitHub công khai: **thu hồi key đó ngay lập tức** tại trang quản lý key tương ứng (GitHub Settings hoặc Groq Console) — dù đã xóa khỏi code, lịch sử Git vẫn giữ lại commit cũ chứa key.
- Mỗi thành viên trong nhóm nên dùng **API key của riêng mình** (không dùng chung 1 key), để tránh tranh chấp hạn ngạch khi nhiều người chạy thực nghiệm cùng lúc.

---

## 9. Các vấn đề đã gặp trong quá trình làm — tham khảo nếu gặp lại

- **Đoán tên thư mục ADR không đáng tin cậy:** mỗi repository đặt tên thư mục ADR khác nhau (có nơi để trong `docs/adr`, có nơi để trong `examples/`, có nơi để ngay ở gốc repo) → giải pháp là chuyển từ dò thư mục cố định sang quét toàn bộ cây thư mục (`1_1_collect_adrs_v2.py`), rồi cuối cùng chuyển hẳn sang tìm kiếm nội dung trên toàn GitHub (`batch4_discovery.py`) mới thực sự hiệu quả.
- **Model LLM bị nhà cung cấp ngừng hỗ trợ đột ngột** (nhóm đã gặp với Gemini 2.0/1.5 Flash, Groq Llama-3.3-70B, Groq Llama-4-Maverick, Groq Gemma2-9B): luôn chạy `check_groq_models.py` trước khi sinh dữ liệu, đừng tin tên model ghi trong tài liệu cũ hoặc code cũ.
- **Thư viện `bert-score` gãy khi dùng chung với `transformers` phiên bản 5.x:** đã ghim `transformers<5` trong `requirements.txt` để tránh lỗi này.
- **Model dạng reasoning (GPT-OSS) trả về output rỗng:** do dùng hết token cho bước suy luận nội bộ trước khi viết câu trả lời thật — đã tăng `max_tokens` và giảm `reasoning_effort` trong code, nhưng nếu vẫn gặp, dùng `2b_cleanup_empty_results.py` rồi chạy lại `2_generation_layer.py`.
- **OpenRouter free tier giới hạn 50 request/ngày nếu tài khoản chưa nạp tiền** (kể cả những request bị lỗi cũng tính vào hạn ngạch này): nhóm đã bỏ hẳn OpenRouter, chuyển toàn bộ 4 model sang chạy qua Groq để tránh giới hạn này.
