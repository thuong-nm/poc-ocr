# Báo cáo dự án img2docx — Chuyển ảnh chụp văn bản hành chính Ả Rập/Anh sang DOCX (on-premise)

*Ngày: 01/10/2026 · Repo: `git@github.com:thuong-nm/poc-ocr.git` (nhánh `master`)*

## 1. Tóm tắt

Đã xây dựng xong một công cụ Python chạy **hoàn toàn offline**. Công cụ nhận ảnh chụp (JPG/PNG/HEIC) văn bản hành chính tiếng Ả Rập, tiếng Anh hoặc song ngữ, và xuất ra:

- file **.docx** chỉnh sửa được: đúng chiều RTL, bảng có ô gộp, header/footer theo letterhead, con dấu/chữ ký chèn dạng ảnh;
- file **JSON trung gian (IR) có version** (schema `1.0.0`): vị trí từng khối, loại khối, độ tin cậy, cờ `needs_review` kèm lý do, metadata (số công văn, ngày Hijri/Gregorian, chữ trên con dấu).

Toàn bộ pipeline, CLI (đơn lẻ + batch), Python API, FastAPI service, bộ sinh dữ liệu tổng hợp, script đánh giá và **50 bài test (pass toàn bộ, 1 xfail có chủ đích)** đều chạy được trên máy dev GTX 1650 4 GB.

**Kết quả chính** (dữ liệu tổng hợp, 36 trang, 3 mức xuống cấp ảnh):

| Cấu hình | CER toàn trang | CER đoạn văn | CER tiếng Anh | Cấu trúc bảng (TEDS-S) | Thứ tự đọc (τ) | Tốc độ |
|---|---|---|---|---|---|---|
| `dev-cpu` (Tesseract + PaddleOCR, 36 trang) | 0.170 | 0.151 | 0.064 | **1.000** | 0.908 | **18.8 s/trang** |
| `dev-cpu` (12 trang "mild") | 0.146 | 0.138 | 0.073 | 1.000 | 0.898 | 17.4 s/trang |
| `dev-vlm` (Qwen3-VL-2B Q4 qua Ollama, 12 trang "mild") | **0.138** | **0.110** | **0.056** | 1.000 | **0.929** | 160 s/trang |

Với cùng 12 trang, VLM tốt hơn rõ ở đoạn văn (0.110 so với 0.138), tiêu đề (0.164 so với 0.343), trích xuất ngày (65% so với 40%) và số công văn (67% so với 50%). Đổi lại, VLM chậm hơn khoảng 9 lần trên card 4 GB.

## 2. Môi trường và ràng buộc

| Hạng mục | Giá trị |
|---|---|
| Máy | Windows + WSL2, Ubuntu 24.04, 8 luồng CPU, 15 GB RAM |
| GPU | GTX 1650 4 GB (Turing, không có bf16; desktop đã chiếm ~1.2 GB) |
| Python | 3.11, môi trường conda cục bộ `./.venv` (không cần sudo) |
| Công cụ cài không cần root | Tesseract 5.5.3 (conda-forge), LibreOffice 26.8 (AppImage giải nén), Ollama 0.35 (tarball) |

## 3. Mô hình và giấy phép (đã kiểm tra trên Hugging Face / Ollama)

Mọi mô hình dùng ở runtime đều là **Apache-2.0**, tương thích thương mại.

| Vai trò | Mô hình | Giấy phép |
|---|---|---|
| Phân tích layout | `PaddlePaddle/PP-DocLayout_plus-L` | Apache-2.0 |
| Xoay trang | `PaddlePaddle/PP-LCNet_x1_0_doc_ori` + Tesseract OSD | Apache-2.0 |
| Nắn cong giấy (tùy chọn) | `PaddlePaddle/UVDoc` | Apache-2.0 |
| OCR cổ điển | Tesseract `ara`+`eng` | Apache-2.0 |
| OCR đối chiếu | `arabic_PP-OCRv5_mobile_rec`, `en_PP-OCRv5_mobile_rec` | Apache-2.0 |
| VLM trên server GPU | `Qwen/Qwen3-VL-8B-Instruct` (vLLM) | Apache-2.0 |
| VLM trên máy dev | Ollama `qwen3-vl:2b-instruct-q4_K_M` | Apache-2.0 |

Các phương án **bị loại**:

- **DocLayout-YOLO**: trọng số là Apache-2.0, nhưng phải chạy bằng bản fork **ultralytics AGPL-3.0**, rủi ro khi phân phối thương mại.
- **DocTr**: không có trọng số với giấy phép rõ ràng.
- **PyMuPDF (AGPL)**: chỉ dùng trong công cụ đánh giá/render, không nằm trong runtime.

## 4. Kiến trúc pipeline

```
ảnh → QA → hình học (tìm khung giấy → warp phối cảnh → [UVDoc] → bỏ phiếu xoay trang → chỉnh nghiêng)
    → làm phẳng ánh sáng → layout (PP-DocLayout + heuristic dòng chữ / màu mực)
    → nhận dạng (engine chính + engine đối chiếu) → hậu xử lý (bidi, ngày, số công văn)
    → thứ tự đọc RTL/LTR (XY-cut) → độ tin cậy → JSON IR → DOCX
```

Mỗi bước là một module riêng, có test riêng (`img2docx/qa.py`, `geometry.py`, `illumination.py`, `layout.py`, `reading_order.py`, `recognizers/`, `postprocess.py`, `schema.py`, `docx_builder.py`, `confidence.py`, `pipeline.py`, `cli.py`, `api.py`).

Ba cấu hình (profile):

- **`dev-cpu`** (mặc định): Tesseract làm engine chính, PaddleOCR đối chiếu. Chạy được trên mọi CPU.
- **`dev-vlm`**: Qwen3-VL-2B qua Ollama, Tesseract đối chiếu. Bảng biểu được chuyển sang Tesseract + nhận dạng lưới kẻ, vì đo được VLM 2B làm hỏng cấu trúc bảng (TEDS ≈ 0.35 so với 0.81).
- **`gpu-server`**: Qwen3-VL-8B qua vLLM, PaddleOCR đối chiếu, có UVDoc. Đã có Dockerfile + docker-compose.

**Gắn LoRA sau này**: cấu hình `recognition.vlm.adapters`, chọn adapter theo loại vùng (`printed` / `handwritten` / `table`…).

- Với vLLM: tên adapter khai báo qua `--lora-modules` và được gửi làm trường `model` của request.
- Với transformers: nạp PEFT một lần, chuyển adapter theo từng request.

## 5. Kết quả đánh giá chi tiết (`dev-cpu`, 36 trang)

**Theo loại khối:**

| Loại khối | Số khối | CER | Độ chính xác phân loại |
|---|---|---|---|
| header (letterhead) | 72 | **0.001** | 1.00 |
| paragraph | 180 | 0.151 | 0.91 |
| title | 48 | 0.342 | 0.81 |
| date | 60 | 0.457 | 0.65 |
| doc_number | 36 | 0.540 | 0.56 |
| footer | 36 | 0.436 | 0.58 |
| handwritten_note | 36 | 0.704 | 0.31 |

**Theo ngôn ngữ:** tiếng Anh 0.064 · tiếng Ả Rập 0.276 · khối song ngữ 0.222.

**Theo mức xuống cấp:** clean 0.196 · mild 0.180 · hard 0.201. Hệ thống ổn định trước phối cảnh, cong giấy, bóng đổ, mờ và nén JPEG.

**Các chỉ số khác:**

- Bảng: TEDS-S **1.000** (cấu trúc ô gộp đúng 100%); TEDS có tính nội dung là 0.788.
- Phát hiện con dấu 1.00, logo 1.00, chữ ký 0.39.
- Thứ tự đọc: Kendall τ 0.908.

**Thử nghiệm UVDoc** (12 trang "hard", có cong giấy):

| | Không UVDoc | Có UVDoc |
|---|---|---|
| CER | 0.201 | 0.193 |
| CER toàn trang | 0.180 | 0.182 |
| Phát hiện con dấu | 1.00 | 0.92 |
| Tốc độ | 18.9 s | 21.6 s |

Lợi ích không đáng kể ở mức cong giấy của bộ dữ liệu này, nên UVDoc để **tắt mặc định** và bật trong profile `gpu-server`. Cần đánh giá lại trên ảnh thật bị cong nhiều.

**Tiến triển qua các vòng sửa lỗi (`dev-cpu`):**

| Chỉ số | v1 | cuối |
|---|---|---|
| CER toàn trang | 0.221 | 0.170 |
| τ thứ tự đọc | 0.84 | 0.91 |
| Phát hiện con dấu | 0.75 | 1.00 |
| Phát hiện chữ ký | 0.14 | 0.39 |
| Tốc độ | 35 s/trang | 19 s/trang |

Báo cáo đầy đủ: `reports/eval_dev-cpu.md`, `reports/eval_dev-vlm_mild.md`, `reports/eval_dev-cpu_uvdoc_hard.md`.

## 6. Các phát hiện quan trọng trong quá trình làm

1. **PP-LCNet xoay nhầm trang Ả Rập đứng thẳng thành 180°** (độ tin cậy 0.91). Đã thay bằng cơ chế bỏ phiếu PP-LCNet + Tesseract OSD. Khi hai bên không đồng ý, hệ thống chạy OCR thử trên cả 4 hướng và chọn hướng có độ tin cậy cao nhất. Đúng 12/12 ca thử.
2. **LibreOffice kế thừa RTL từ style** khiến đoạn tiếng Anh bị căn phải. Bài test render qua LibreOffice đã bắt được lỗi này. Cách sửa: luôn ghi `w:bidi w:val="0"` cho đoạn LTR, và đặt `w:bidiVisual` tường minh cho bảng header.
3. **Tesseract tự phân đoạn sai dòng tiếng Ả Rập** (cắt một dòng thành nhiều cột). Đã chuyển sang dùng phân đoạn dòng riêng của hệ thống, rồi OCR từng dòng với `--psm 7` và thử lại ở nhiều tỉ lệ.
4. **PaddleOCR Ả Rập nhận dạng rất kém dòng dài.** Trên CPU, việc phát hiện chữ cho cả trang mất 24 s. Đã đổi sang chia dòng theo khoảng trắng giữa các từ và chỉ chạy bộ nhận dạng: nhanh hơn khoảng 3 lần và chính xác hơn nhiều.
5. **Chữ số Ả Rập-Ấn (٠-٩):** Tesseract đọc sai (`٣/٣٧٤٥` thành `P/PVEO`). PaddleOCR đọc đúng chữ số nhưng bỏ mất `/` và `:`. Phép so khớp giữa hai engine giờ chỉ bỏ qua chữ số Latin, nên các dòng này bị gắn cờ review thay vì đoán.
6. **VLM 2B lượng tử Q4:**
   - đôi khi **thêm dấu tashkeel không có trong ảnh** (vi phạm nguyên tắc trung thực) → được gắn cờ review;
   - **đảo thứ tự cụm số** → với dòng nhiều chữ số, ưu tiên Tesseract khi Tesseract tự tin;
   - xuất HTML bảng kèm thuộc tính rác → đã làm sạch.

   Phiên bản Q8 không tốt hơn Q4 (micro-CER 0.233 so với 0.193). Bản 2B full-precision chạy bằng transformers đọc đúng hoàn toàn đoạn văn mẫu, cho thấy lượng tử hóa làm giảm chất lượng.
7. **Hộp `image` của layout model thường bao cả con dấu lẫn chữ ký** → đã thêm bước tách bằng Hough circle + tách theo cụm màu mực. Chữ in nằm dưới con dấu vẫn được OCR riêng.

## 7. Hạn chế đã biết

- **Chữ viết tay**: engine cổ điển gần như không đọc được (CER ≈ 0.70). VLM 2B chỉ đọc được ghi chú ngắn. Mọi khối viết tay luôn được gắn `needs_review`.
- **Số công văn / ngày tháng dùng chữ số Ả Rập-Ấn**: CER 0.45–0.54 với `dev-cpu`, giảm còn 0.29–0.32 với VLM. Trên server cần dùng bản 8B, hoặc phải có người duyệt.
- **Font nhiều chữ ghép (Amiri), basmala có đầy đủ tashkeel, thư pháp**: Tesseract kém (CER ~0.45 trên một số trang).
- **Phát hiện chữ ký/chữ viết tay** dựa trên màu mực. Chữ viết tay bằng mực đen sẽ bị coi là chữ in; lúc đó độ tin cậy thấp là tấm lưới an toàn.
- Hiện **gần như mọi trang đều bị gắn `needs_review`**, vì trang tổng hợp nào cũng có ghi chú viết tay (theo đúng thiết kế, khối viết tay luôn cần duyệt). Với tài liệu thật cần hiệu chỉnh ngưỡng.
- Có **4 khối bị cắt cụt do giới hạn `max_tokens`** của VLM. Cần nới hệ số `tokens_per_line_factor`.
- Kết quả VLM thay đổi nhẹ giữa các lần chạy: CER 0.122 ở lần chạy trước, 0.140 ở lần chạy cuối.
- Tất cả số liệu đo trên **dữ liệu tổng hợp**. Cần một bộ ảnh thật có nhãn để đánh giá chính thức.

## 8. Những gì chưa kiểm chứng được trên máy này

- **vLLM + Qwen3-VL-8B**: code và cấu hình đã sẵn sàng (backend OpenAI-compatible dùng chung với Ollama), nhưng không chạy được trên GPU 4 GB, nên chưa đo.
- **Dockerfile / docker-compose (CUDA)**: đã viết, chưa build thử trên máy này.
- **Backend transformers**: đã chạy thử thành công trên CPU, một crop đoạn văn, khoảng 47 s. Chưa đo trên toàn bộ dữ liệu.
- **Paddle chạy trên GPU**: bản cài hiện tại là paddle CPU. Code có tự động fallback về CPU.

## 9. Hướng dẫn nhanh

```bash
img2docx anh.jpg -o out/vanban.docx --debug-dir dbg/            # một ảnh (mặc định dev-cpu)
img2docx anh.jpg -o out/vanban.docx --profile dev-vlm           # dùng Qwen3-VL-2B qua Ollama
img2docx batch thu_muc_anh/ -o out/ --workers 4                 # xử lý hàng loạt, báo cáo pages/s
img2docx serve --port 8080                                      # REST API: POST /convert
pytest -q                                                       # chạy toàn bộ test
python scripts/evaluate.py data/synth -o reports/eval.md --profile dev-cpu
```

Cài đặt (cần mạng một lần) và các cấu hình khác: xem `README.md` và `config.example.yaml`.

## 10. Đề xuất bước tiếp theo

1. Thu thập 50–100 ảnh văn bản thật (đã che thông tin nhạy cảm) và gán nhãn bằng chính JSON IR, để đánh giá thực tế.
2. Triển khai `gpu-server` (Qwen3-VL-8B qua vLLM) và đo lại. Kỳ vọng cải thiện lớn ở chữ số Ả Rập-Ấn và chữ viết tay.
3. Fine-tune LoRA cho chữ in và chữ viết tay. Pipeline đã có sẵn chỗ gắn adapter, và bộ sinh dữ liệu tổng hợp cung cấp dữ liệu khởi đầu.
4. Bổ sung kết hợp kết quả hai engine ở mức ký tự cho các dòng số: lấy chữ số từ PaddleOCR, dấu `/` và `:` từ Tesseract, kèm cờ review.
5. Nới ngân sách `max_tokens` cho VLM và đo lại.
