import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path


SPLIT_SCRIPT = "split_shopify_products.py"
MIGRATE_SCRIPT = "migrate_rich_description_images.py"
ENV_FILENAME = ".upload.env"
HANDLE_COLUMN = "Handle"
MAX_PRODUCTS_CSV_NUMBER = 50


def run_command(command, title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    print("Command:")
    print(
        " ".join(
            f'"{x}"' if " " in str(x) else str(x)
            for x in command
        )
    )
    print()

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            f"\nBước thất bại: {title}\n"
            f"Exit code: {result.returncode}"
        )


def count_products_by_handle(input_csv: Path):
    with input_csv.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise RuntimeError("Không đọc được header CSV.")

        if HANDLE_COLUMN not in reader.fieldnames:
            raise RuntimeError(
                f"CSV không có column '{HANDLE_COLUMN}'."
            )

        handles = {
            (row.get(HANDLE_COLUMN, "") or "").strip()
            for row in reader
            if (row.get(HANDLE_COLUMN, "") or "").strip()
        }

    if not handles:
        raise RuntimeError("CSV không có product Handle hợp lệ.")

    return len(handles)


def resolve_script(script_dir: Path, value: str):
    path = Path(value)

    if not path.is_absolute():
        path = script_dir / path

    return path.resolve()


def expected_split_paths(
    input_csv: Path,
    total_products: int,
    max_products: int,
):
    part_count = math.ceil(total_products / max_products)

    return [
        input_csv.parent / f"{input_csv.stem}_part_{i}.csv"
        for i in range(1, part_count + 1)
    ]


def output_path_for(csv_path: Path):
    return csv_path.parent / f"{csv_path.stem}_shopify_files.csv"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Flow xử lý Shopify Products CSV:\n"
            "1. Đếm product theo Handle\n"
            "2. Nếu > MAX_PRODUCTS_CSV_NUMBER thì split thành các part\n"
            "3. Upload Amazon Rich Description images vào Shopify "
            "Content > Files\n"
            "4. Replace bằng Shopify CDN URL"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "input_csv",
        help="Đường dẫn tới Shopify Products export CSV gốc",
    )

    parser.add_argument(
        "--max-products",
        type=int,
        default=MAX_PRODUCTS_CSV_NUMBER,
        help=(
            "Số product tối đa mỗi CSV trước khi phải split. "
            f"Default: {MAX_PRODUCTS_CSV_NUMBER}"
        ),
    )

    parser.add_argument(
        "--split-script",
        default=SPLIT_SCRIPT,
        help=f"Script chia CSV. Default: {SPLIT_SCRIPT}",
    )

    parser.add_argument(
        "--migrate-script",
        default=MIGRATE_SCRIPT,
        help=f"Script migrate ảnh. Default: {MIGRATE_SCRIPT}",
    )

    parser.add_argument(
        "--env",
        dest="env_path",
        help=(
            "Path tới .upload.env. Default: .upload.env cùng cấp flow.py"
        ),
    )

    args = parser.parse_args()

    if args.max_products < 1:
        raise ValueError("--max-products phải >= 1.")

    input_csv = Path(args.input_csv).expanduser().resolve()

    if not input_csv.exists():
        raise FileNotFoundError(
            f"Không tìm thấy input CSV:\n{input_csv}"
        )

    script_dir = Path(__file__).resolve().parent
    split_script = resolve_script(script_dir, args.split_script)
    migrate_script = resolve_script(script_dir, args.migrate_script)

    if not migrate_script.exists():
        raise FileNotFoundError(
            f"Không tìm thấy script migrate:\n{migrate_script}"
        )

    if args.env_path:
        env_path = Path(args.env_path).expanduser().resolve()
    else:
        env_path = script_dir / ENV_FILENAME

    # .upload.env chỉ cần khi migration có Amazon images, nhưng kiểm tra
    # existence ngay từ flow để lỗi cấu hình hiển thị sớm và rõ ràng.
    if not env_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy .upload.env:\n{env_path}"
        )

    total_products = count_products_by_handle(input_csv)

    print("=" * 80)
    print("WRYDECO SHOPIFY FILES FLOW")
    print("=" * 80)
    print(f"Input CSV       : {input_csv}")
    print(f"Products        : {total_products}")
    print(f"Max products    : {args.max_products}")
    print(f"Upload env      : {env_path}")

    files_to_migrate = []
    intermediate_files = []

    # ============================================================
    # STEP 1: CONDITIONAL SPLIT
    # ============================================================
    if total_products > args.max_products:
        if not split_script.exists():
            raise FileNotFoundError(
                f"Không tìm thấy script chia file:\n{split_script}"
            )

        print()
        print(
            f"[SPLIT] {total_products} > {args.max_products}: "
            "sẽ chia CSV."
        )

        run_command(
            [
                sys.executable,
                str(split_script),
                str(input_csv),
                "--max-products",
                str(args.max_products),
            ],
            "STEP 1 - SPLIT CSV THEO PRODUCT HANDLE",
        )

        files_to_migrate = expected_split_paths(
            input_csv=input_csv,
            total_products=total_products,
            max_products=args.max_products,
        )

        missing = [path for path in files_to_migrate if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Split chạy xong nhưng thiếu output:\n"
                + "\n".join(str(x) for x in missing)
            )

        intermediate_files = list(files_to_migrate)
    else:
        print()
        print(
            f"[NO SPLIT] {total_products} <= {args.max_products}: "
            "migrate trực tiếp CSV đầu vào."
        )
        files_to_migrate = [input_csv]

    # ============================================================
    # STEP 2: MIGRATE EACH INPUT TO SHOPIFY CONTENT > FILES
    # ============================================================
    # Dùng 1 cache chung cho toàn flow để cùng một Amazon URL không bị
    # upload trùng nếu xuất hiện ở nhiều part/product.
    shared_cache = (
        input_csv.parent
        / f"{input_csv.stem}_shopify_upload_cache.json"
    )

    final_outputs = []

    for index, csv_path in enumerate(files_to_migrate, start=1):
        output_path = output_path_for(csv_path)

        run_command(
            [
                sys.executable,
                str(migrate_script),
                str(csv_path),
                "--output",
                str(output_path),
                "--cache",
                str(shared_cache),
                "--env",
                str(env_path),
            ],
            (
                f"MIGRATE {index}/{len(files_to_migrate)} - "
                "SHOPIFY CONTENT > FILES"
            ),
        )

        if not output_path.exists():
            raise FileNotFoundError(
                "Migrate chạy xong nhưng không thấy output:\n"
                f"{output_path}"
            )

        final_outputs.append(output_path)

    # ============================================================
    # DONE
    # ============================================================
    print()
    print("=" * 80)
    print("FLOW COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print()
    print("File cuối cùng để import Shopify:")

    for i, path in enumerate(final_outputs, start=1):
        print(f"  {i}. {path}")

    if intermediate_files:
        print()
        print("File split trung gian:")
        for i, path in enumerate(intermediate_files, start=1):
            print(f"  {i}. {path}")

    print()
    print(f"Shared upload cache: {shared_cache}")
    print()
    print(
        "Safety: amazon_link vẫn hard-lock; chỉ Amazon image URL trong "
        "Rich Description được replace bằng Shopify CDN URL."
    )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\n\nĐã dừng bởi người dùng.")
        sys.exit(130)

    except Exception as exc:
        print()
        print("=" * 80)
        print("FLOW FAILED")
        print("=" * 80)
        print(exc)
        sys.exit(1)
