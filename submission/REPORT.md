# Báo cáo Day 09 — Lê Minh Thắng, 2A202603292

## 1. Kết luận trước

Pipeline kết luận **Hold**. Trong 224 ảnh đầu vào, pipeline loại 31 ảnh ở bước tiếp nhận và xuất 193 ảnh vào `submission/export/clean_v1` dưới dạng bản nháp để thử nghiệm.

Sau lượt duyệt mô phỏng, còn 0 lỗi bắt buộc và 34/193 ảnh (17,62%) có cảnh báo chưa được duyệt. Tỷ lệ này vượt ngưỡng 10% nên lô dữ liệu bị tạm giữ.

## 2. Lỗi và phân việc

Bảng tổng hợp từ 216 dòng trong `02_error_list_v1.csv`. Lô đầu vào có 224 ảnh, trong đó 193 ảnh qua bước tiếp nhận.

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy | Loại ảnh không mở được. |
| `BAD_SIZE` | 3 ảnh | Máy | Loại ảnh có cạnh ngắn dưới ngưỡng. |
| `DUP_IMAGE_NEAR` | 7 ảnh | Máy | Loại ảnh gần trùng theo ngưỡng pHash. |
| `LEAK_TEST` | 11 ảnh | Máy | Loại ảnh trùng với tập tham chiếu để tránh rò rỉ dữ liệu. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy | Loại ảnh trùng nguyên bản. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người | Cần xem ảnh và bổ sung nhãn. |
| `EMPTY_LABEL` | 11 ảnh | Người | Cần xác nhận ảnh có vật thể cần gán nhãn hay không. |
| `DUP_BOX` | 7 dòng | Máy | Xóa dòng box trùng xuất hiện sau. |
| `BAD_FORMAT` | 3 dòng | Máy | Xóa dòng nhãn sai định dạng. |
| `BOX_HUGE` | 3 dòng / 3 ảnh | Người | Kiểm tra box lớn có thực sự ôm đúng vật thể. |
| `BAD_CLASS_ID` | 6 dòng | Máy | Xóa dòng có ID lớp ngoài danh sách hợp lệ. |
| `BOX_TINY` | 6 dòng / 4 ảnh | Người | Kiểm tra box nhỏ theo quy tắc gán nhãn. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy | Cắt box về trong ảnh hoặc xóa dòng nếu box hết diện tích. |
| `BOX_ZERO` | 4 dòng | Máy | Xóa dòng có chiều rộng hoặc chiều cao không dương. |
| `BAD_CLASS_NAME` | 2 dòng báo cáo | Máy | Chuẩn hóa tên lớp trong `data.yaml` theo cấu hình. |
| `CLASS_RARE` | 4 dòng báo cáo | Người | Đánh giá lớp ít mẫu ở cấp bộ dữ liệu. |
| `POSSIBLE_MISSING` | 53 cảnh báo / 52 ảnh | Người | Xác nhận vật thể có bị thiếu box. |
| `POSSIBLE_LOOSE_BOX` | 27 cảnh báo / 23 ảnh | Người | Kiểm tra box có lỏng hoặc lệch. |
| `POSSIBLE_WRONG_CLASS` | 17 cảnh báo / 17 ảnh | Người | Xác nhận lớp đúng của vật thể. |
| `POSSIBLE_FALSE_POS` | 28 cảnh báo / 26 ảnh | Người | Xác nhận box có bị gán thừa. |

Trong `05_review_queue.csv`, `img_0020` đứng đầu với điểm ưu tiên **11,524** vì có đồng thời ba cờ `FIXED_DROP_LINE`, `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS`.

Theo `06_review_log.csv`, lượt duyệt mô phỏng đã xử lý **80/121 ảnh** trong hàng đợi. Trong số đó, **74/80 ảnh** có ít nhất một cảnh báo ngữ nghĩa (`POSSIBLE_*`). Tổng cộng có **88 lượt mã cảnh báo ngữ nghĩa theo ảnh** được đưa vào lượt duyệt. Một ảnh có thể mang nhiều mã và mỗi cảnh báo là một trường hợp cần xác minh.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do chọn |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 16 | Ảnh gần trùng: P 1,00 → 1,00; R 0,50 → 0,83 | Phát hiện 5/6 ảnh gần trùng, so với 3/6 ban đầu. Cả 5 ảnh bị đánh dấu đều đúng trên tập calibration. |
| `second_opinion.conf` | 0,25 | 0,60 | Thiếu nhãn: P 0,50 → 0,57; R 1,00 → 1,00 | Vẫn phát hiện đủ 8/8 ca thiếu nhãn. Đổi lại, số ca box lỏng phát hiện được giảm từ 2/5 xuống 1/5. |

Điểm dễ đánh giá sai là lấy precision 1,00 trên tập calibration để kết luận ngưỡng pHash 16 cũng chính xác trên lô thực tế. Con số này dựa trên 5/5 ảnh được đánh dấu đúng trong tập calibration. Trên lô thực tế, `02_error_list_v1.csv` ghi nhận 7/224 ảnh bị loại vì `DUP_IMAGE_NEAR`. Cần đối chiếu các cặp ảnh này để xác nhận có ảnh nào bị loại nhầm.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Kiểm tra cửa chặn.** Khi chạy với `--budget 0`, pipeline tiếp nhận 193/224 ảnh và không có ảnh nào được duyệt. Cuối lượt chạy vẫn còn 6 lỗi bắt buộc. Gate kết luận **Rework**, trả mã thoát `20` và chặn xuất dataset sang `work/exp_nb`.
**(b) Hai điểm mù quan sát được.**

- **Box gán nhầm `person` — `img_0005.png`.** Khi xem ảnh trong `work/viz`, đối tượng có `object_id 5` được gán nhãn `person` dù đối tượng trong box không phải người. Báo cáo `02_error_list_v1.csv` không có cảnh báo nào cho ảnh này.
- **Thiếu box `car` — `img_0007.png`.** Khi xem ảnh trong `work/viz`, tôi thấy một xe hơi chưa có box `car`. Báo cáo `02_error_list_v1.csv` không có cảnh báo nào cho ảnh này.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa train: ghi "chưa chạy" và lý do, rồi bỏ qua phần còn lại của mục này. Nếu đã train: dán bảng từ `submission/results/comparison.md` (model, epoch, seed, số ảnh train mỗi biến thể).

Chưa chạy. Tôi ưu tiên hoàn thành phần lõi của lab trước khi thực hiện thí nghiệm so sánh raw và clean trên Colab.
## 6. Quyết định và ghi chú AI
Quyết định cuối là **Hold**. Với 193 ảnh và 0 lỗi bắt buộc, cần xử lý hoặc duyệt thêm ít nhất 15 trong 34 ảnh còn cảnh báo để giảm xuống tối đa 19/193 ảnh (9,84%), dưới ngưỡng 10%. Sau đó chạy lại pipeline để xác nhận **Release**.

*(Thưởng +2, tùy chọn)* CVAT: lọc `width < 20`, ảnh/số box khớp, đối chiếu `BOX_TINY` (xem docs/CVAT_FILTER.md), 1 câu về `can_review`.
