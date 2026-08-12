import argparse
import csv
from collections import OrderedDict
from pathlib import Path

HANDLE_COLUMN = "Handle"


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


def split_shopify_csv(input_path: Path):
    fieldnames, rows = read_csv(input_path)

    if HANDLE_COLUMN not in fieldnames:
        raise RuntimeError(f"CSV không có column '{HANDLE_COLUMN}'.")

    # ========================================================
    # GROUP ROWS BY PRODUCT HANDLE
    # ========================================================

    products = OrderedDict()

    rows_without_handle = []

    for row in rows:
        handle = (row.get(HANDLE_COLUMN, "") or "").strip()

        if not handle:
            rows_without_handle.append(row)
            continue

        products.setdefault(
            handle,
            [],
        ).append(row)

    handles = list(products.keys())

    total_products = len(handles)

    if total_products < 2:
        raise RuntimeError("File cần ít nhất 2 sản phẩm để chia.")

    # ========================================================
    # SPLIT PRODUCT LIST 50 / 50
    # ========================================================

    # Nếu số product lẻ:
    # part 1 sẽ nhiều hơn part 2 đúng 1 product.
    split_index = (total_products + 1) // 2

    part1_handles = handles[:split_index]
    part2_handles = handles[split_index:]

    part1_handle_set = set(part1_handles)
    part2_handle_set = set(part2_handles)

    # ========================================================
    # SAFETY CHECK: NO DUPLICATE PRODUCT
    # ========================================================

    overlap = part1_handle_set & part2_handle_set

    if overlap:
        raise RuntimeError(
            "CRITICAL ERROR: Có sản phẩm bị trùng giữa " f"2 file: {sorted(overlap)}"
        )

    # ========================================================
    # BUILD ROWS
    # ========================================================

    part1_rows = []
    part2_rows = []

    # Giữ nguyên thứ tự gốc của CSV
    for row in rows:
        handle = (row.get(HANDLE_COLUMN, "") or "").strip()

        if not handle:
            # Trường hợp cực hiếm có row không Handle.
            #
            # Để không làm mất dữ liệu, đưa vào part 1.
            part1_rows.append(row)
            continue

        if handle in part1_handle_set:
            part1_rows.append(row)

        elif handle in part2_handle_set:
            part2_rows.append(row)

        else:
            raise RuntimeError(f"Không xác định được product: {handle}")

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    handles_in_part1 = {
        (row.get(HANDLE_COLUMN, "") or "").strip()
        for row in part1_rows
        if (row.get(HANDLE_COLUMN, "") or "").strip()
    }

    handles_in_part2 = {
        (row.get(HANDLE_COLUMN, "") or "").strip()
        for row in part2_rows
        if (row.get(HANDLE_COLUMN, "") or "").strip()
    }

    duplicate_handles = handles_in_part1 & handles_in_part2

    if duplicate_handles:
        raise RuntimeError(
            "CRITICAL ERROR: Product xuất hiện "
            "trong cả hai file:\n" + "\n".join(sorted(duplicate_handles))
        )

    # Tổng product phải giữ nguyên
    if len(handles_in_part1) + len(handles_in_part2) != total_products:
        raise RuntimeError(
            "CRITICAL ERROR: Tổng số product " "sau khi split không đúng."
        )

    # Tổng row phải giữ nguyên
    if len(part1_rows) + len(part2_rows) != len(rows):
        raise RuntimeError("CRITICAL ERROR: Tổng số row " "sau khi split không đúng.")

    # ========================================================
    # OUTPUT PATHS
    # ========================================================

    output_part1 = input_path.parent / f"{input_path.stem}_part_1.csv"

    output_part2 = input_path.parent / f"{input_path.stem}_part_2.csv"

    # ========================================================
    # WRITE
    # ========================================================

    write_csv(
        output_part1,
        fieldnames,
        part1_rows,
    )

    write_csv(
        output_part2,
        fieldnames,
        part2_rows,
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print("=" * 70)
    print("SHOPIFY CSV SPLIT COMPLETED")
    print("=" * 70)

    print(f"Input:")
    print(f"  {input_path}")

    print()

    print(f"Total products : {total_products}")
    print(f"Total rows     : {len(rows)}")

    print()

    print("PART 1")
    print(f"  Products : " f"{len(handles_in_part1)}")
    print(f"  Rows     : " f"{len(part1_rows)}")
    print(f"  File     : " f"{output_part1}")

    print()

    print("PART 2")
    print(f"  Products : " f"{len(handles_in_part2)}")
    print(f"  Rows     : " f"{len(part2_rows)}")
    print(f"  File     : " f"{output_part2}")

    print()

    print("[OK] Không có product nào " "xuất hiện ở cả 2 file.")

    print("[OK] Mỗi product được giữ nguyên " "toàn bộ rows / variants / images.")

    print("[OK] Thứ tự rows của Shopify " "được giữ nguyên.")

    if rows_without_handle:
        print()
        print(
            f"[WARNING] Có "
            f"{len(rows_without_handle)} "
            f"row không có Handle. "
            f"Các row này được đưa vào part 1."
        )

    return output_part1, output_part2


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Split Shopify Products export CSV "
            "into 2 files without splitting products."
        )
    )

    parser.add_argument(
        "input_csv",
        help="Shopify Products export CSV",
    )

    args = parser.parse_args()

    input_path = Path(args.input_csv).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path}")

    split_shopify_csv(input_path)


if __name__ == "__main__":
    main()
