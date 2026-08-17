import argparse
import csv
import math
from collections import OrderedDict
from pathlib import Path


HANDLE_COLUMN = "Handle"
MAX_PRODUCTS_CSV_NUMBER = 50


def read_csv(csv_path: Path):
    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise RuntimeError("Không đọc được header CSV.")

        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    return fieldnames, rows


def write_csv(output_path: Path, fieldnames, rows):
    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def group_rows_by_handle(rows):
    products = OrderedDict()
    rows_without_handle = []

    for row in rows:
        handle = (row.get(HANDLE_COLUMN, "") or "").strip()

        if not handle:
            rows_without_handle.append(row)
            continue

        products.setdefault(handle, []).append(row)

    return products, rows_without_handle


def count_products(input_path: Path):
    fieldnames, rows = read_csv(input_path)

    if HANDLE_COLUMN not in fieldnames:
        raise RuntimeError(f"CSV không có column '{HANDLE_COLUMN}'.")

    products, _ = group_rows_by_handle(rows)
    return len(products)


def split_shopify_csv(
    input_path: Path,
    max_products: int = MAX_PRODUCTS_CSV_NUMBER,
):
    if max_products < 1:
        raise ValueError("max_products phải >= 1.")

    fieldnames, rows = read_csv(input_path)

    if HANDLE_COLUMN not in fieldnames:
        raise RuntimeError(f"CSV không có column '{HANDLE_COLUMN}'.")

    products, rows_without_handle = group_rows_by_handle(rows)
    handles = list(products.keys())
    total_products = len(handles)

    if total_products == 0:
        raise RuntimeError("CSV không có product Handle hợp lệ.")

    if total_products <= max_products:
        print("=" * 70)
        print("SHOPIFY CSV SPLIT SKIPPED")
        print("=" * 70)
        print(f"Input        : {input_path}")
        print(f"Products     : {total_products}")
        print(f"Max / file   : {max_products}")
        print("[OK] Không cần split.")
        return [input_path]

    # Mỗi part chứa tối đa max_products Handle và không bao giờ cắt
    # variants/images của cùng một product sang part khác.
    part_handle_lists = [
        handles[start:start + max_products]
        for start in range(0, total_products, max_products)
    ]

    part_handle_sets = [set(part) for part in part_handle_lists]

    # --------------------------------------------------------
    # SAFETY: mọi Handle phải xuất hiện đúng 1 part
    # --------------------------------------------------------
    seen = set()
    for part_number, handle_set in enumerate(part_handle_sets, start=1):
        overlap = seen & handle_set
        if overlap:
            raise RuntimeError(
                "CRITICAL ERROR: Product bị trùng giữa các part: "
                f"part {part_number}: {sorted(overlap)}"
            )
        seen.update(handle_set)

    if seen != set(handles):
        raise RuntimeError(
            "CRITICAL ERROR: Tập Handle sau split không khớp input."
        )

    # --------------------------------------------------------
    # BUILD ROWS - giữ thứ tự gốc trong từng part
    # --------------------------------------------------------
    part_rows = [[] for _ in part_handle_lists]
    handle_to_part = {}

    for part_index, handle_list in enumerate(part_handle_lists):
        for handle in handle_list:
            handle_to_part[handle] = part_index

    for row in rows:
        handle = (row.get(HANDLE_COLUMN, "") or "").strip()

        if not handle:
            # Giữ nguyên policy cũ: row không Handle được đưa vào part 1
            # để không làm mất dữ liệu.
            part_rows[0].append(row)
            continue

        part_index = handle_to_part.get(handle)
        if part_index is None:
            raise RuntimeError(f"Không xác định được product: {handle}")

        part_rows[part_index].append(row)

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------
    if sum(len(x) for x in part_rows) != len(rows):
        raise RuntimeError(
            "CRITICAL ERROR: Tổng số row sau split không đúng."
        )

    handles_after = []
    for rows_in_part in part_rows:
        handles_in_part = {
            (row.get(HANDLE_COLUMN, "") or "").strip()
            for row in rows_in_part
            if (row.get(HANDLE_COLUMN, "") or "").strip()
        }

        if len(handles_in_part) > max_products:
            raise RuntimeError(
                "CRITICAL ERROR: Một part vượt quá max_products."
            )

        handles_after.extend(handles_in_part)

    if len(handles_after) != total_products:
        raise RuntimeError(
            "CRITICAL ERROR: Tổng số product sau split không đúng."
        )

    if len(set(handles_after)) != total_products:
        raise RuntimeError(
            "CRITICAL ERROR: Có product xuất hiện ở nhiều part."
        )

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------
    output_paths = []

    for part_number, rows_in_part in enumerate(part_rows, start=1):
        output_path = (
            input_path.parent
            / f"{input_path.stem}_part_{part_number}.csv"
        )

        write_csv(output_path, fieldnames, rows_in_part)
        output_paths.append(output_path)

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------
    print("=" * 70)
    print("SHOPIFY CSV SPLIT COMPLETED")
    print("=" * 70)
    print(f"Input        : {input_path}")
    print(f"Products     : {total_products}")
    print(f"Rows         : {len(rows)}")
    print(f"Max / file   : {max_products}")
    print(f"Parts        : {math.ceil(total_products / max_products)}")
    print()

    for part_number, (path, handle_list, rows_in_part) in enumerate(
        zip(output_paths, part_handle_lists, part_rows),
        start=1,
    ):
        print(f"PART {part_number}")
        print(f"  Products : {len(handle_list)}")
        print(f"  Rows     : {len(rows_in_part)}")
        print(f"  File     : {path}")

    print("[OK] Không có product nào xuất hiện ở nhiều part.")
    print("[OK] Mỗi product giữ nguyên toàn bộ rows / variants / images.")
    print("[OK] Thứ tự rows của Shopify được giữ nguyên trong từng part.")

    if rows_without_handle:
        print(
            f"[WARNING] Có {len(rows_without_handle)} row không có Handle; "
            "các row này được đưa vào part 1."
        )

    return output_paths


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Split Shopify Products CSV thành nhiều part, "
            "mỗi part tối đa N product Handle và không cắt product."
        )
    )

    parser.add_argument(
        "input_csv",
        help="Shopify Products export CSV",
    )

    parser.add_argument(
        "--max-products",
        type=int,
        default=MAX_PRODUCTS_CSV_NUMBER,
        help=(
            "Số product Handle tối đa mỗi file. "
            f"Default: {MAX_PRODUCTS_CSV_NUMBER}"
        ),
    )

    args = parser.parse_args()

    input_path = Path(args.input_csv).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path}")

    split_shopify_csv(
        input_path=input_path,
        max_products=args.max_products,
    )


if __name__ == "__main__":
    main()
