"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    changes = []
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    remove_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    remove_stems = set()
    missing_stems = set()
    line_errors = defaultdict(lambda: defaultdict(set))
    rename_classes = False

    def record(image, line, action, before, after):
        changes.append(dict(
            image=image, line=line, action=action, before=before, after=after,
        ))

    for issue in issues:
        if issue.severity != ERROR:
            continue
        if issue.code.startswith("DUP_IMAGE_") or issue.code in remove_codes:
            remove_stems.add(issue.image)
        elif issue.code == "MISSING_LABEL_FILE":
            missing_stems.add(issue.image)
        elif issue.code == "BAD_CLASS_NAME":
            rename_classes = True
        elif (issue.code in drop_codes or issue.code == "BOX_OUT_OF_IMAGE"):
            if issue.line is not None:
                line_errors[issue.image][issue.line].add(issue.code)

    # Xóa ảnh trước; không xử lý thêm lỗi dòng của những ảnh này.
    image_paths = defaultdict(list)
    for path in ds.image_files():
        image_paths[path.stem].append(path)
    for stem in sorted(remove_stems):
        paths = image_paths[stem] + [ds.label_path(stem)]
        existing_paths = [path for path in paths if path.exists()]
        if existing_paths:
            before = "; ".join(str(path) for path in existing_paths)
            for path in existing_paths:
                path.unlink()
            record(stem, None, "remove_image", before, "")

    if rename_classes and ds.yaml_path.exists():
        expected_names = dict(enumerate(cfg["classes"]))
        if ds.yaml_names() != expected_names:
            before = ds.yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(before) or {}
            data["names"] = list(cfg["classes"])
            after = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            ds.yaml_path.write_text(after, encoding="utf-8")
            record("data.yaml", None, "rename_classes", before, after)

    for stem in sorted(missing_stems - remove_stems):
        if not ds.label_path(stem).exists():
            record(stem, None, "needs_label", "(không có file)", "chuyển người gán")

    for stem, errors_by_line in sorted(line_errors.items()):
        path = ds.label_path(stem)
        if stem in remove_stems or not path.exists():
            continue

        original = path.read_text(encoding="utf-8", errors="replace")
        output = []
        changed = False
        # Giữ cả dòng trống và ký tự xuống dòng; chỉ ghi file một lần.
        for line_number, raw_line in enumerate(original.splitlines(keepends=True), 1):
            codes = errors_by_line.get(line_number, set())
            before = raw_line.rstrip("\r\n")
            if codes & drop_codes:
                record(stem, line_number, "drop_line", before, "")
                changed = True
                continue

            if "BOX_OUT_OF_IMAGE" in codes:
                try:
                    class_id, cx, cy, w, h = parse_yolo_line(before)
                except ValueError:
                    output.append(raw_line)
                    continue

                left, top = cx - w / 2, cy - h / 2
                right, bottom = cx + w / 2, cy + h / 2
                x1, y1 = max(0.0, left), max(0.0, top)
                x2, y2 = min(1.0, right), min(1.0, bottom)
                if x2 <= x1 or y2 <= y1:
                    record(stem, line_number, "drop_line", before, "")
                    changed = True
                    continue

                if (x1, y1, x2, y2) != (left, top, right, bottom):
                    clipped = ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
                    after = f"{class_id} " + " ".join(f"{v:.12g}" for v in clipped)
                    ending = raw_line[len(before):]
                    output.append(after + ending)
                    record(stem, line_number, "clip_box", before, after)
                    changed = True
                    continue

            output.append(raw_line)

        if changed:
            path.write_text("".join(output), encoding="utf-8")

    return changes
