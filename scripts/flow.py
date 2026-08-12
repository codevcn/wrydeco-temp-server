import argparse
import subprocess
import sys
from pathlib import Path


SPLIT_SCRIPT = "split_shopify_products.py"
MIGRATE_SCRIPT = "migrate_rich_description_images.py"


def run_command(command, title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    print("Command:")
    print(" ".join(f'"{x}"' if " " in str(x) else str(x) for x in command))
    print()

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            f"\nBước thất bại: {title}\n"
            f"Exit code: {result.returncode}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Flow xử lý Shopify Products CSV:\n"
            "1. Chia CSV thành 2 phần theo product Handle\n"
            "2. Thay Amazon image URLs trong Rich Description "
            "cho từng phần bằng URL từ Wrydeco server"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "input_csv",
        help="Đường dẫn tới Shopify Products export CSV gốc",
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

    args = parser.parse_args()

    input_csv = Path(args.input_csv).expanduser().resolve()

    if not input_csv.exists():
        raise FileNotFoundError(
            f"Không tìm thấy input CSV:\n{input_csv}"
        )

    script_dir = Path(__file__).resolve().parent

    split_script = Path(args.split_script)
    if not split_script.is_absolute():
        split_script = script_dir / split_script
    split_script = split_script.resolve()

    migrate_script = Path(args.migrate_script)
    if not migrate_script.is_absolute():
        migrate_script = script_dir / migrate_script
    migrate_script = migrate_script.resolve()

    if not split_script.exists():
        raise FileNotFoundError(
            f"Không tìm thấy script chia file:\n{split_script}"
        )

    if not migrate_script.exists():
        raise FileNotFoundError(
            f"Không tìm thấy script migrate:\n{migrate_script}"
        )

    # ============================================================
    # STEP 1: SPLIT CSV
    # ============================================================

    run_command(
        [
            sys.executable,
            str(split_script),
            str(input_csv),
        ],
        "STEP 1/3 - CHIA CSV THÀNH 2 FILE",
    )

    part1 = (
        input_csv.parent
        / f"{input_csv.stem}_part_1.csv"
    )

    part2 = (
        input_csv.parent
        / f"{input_csv.stem}_part_2.csv"
    )

    if not part1.exists():
        raise FileNotFoundError(
            f"Split hoàn tất nhưng không tìm thấy part 1:\n{part1}"
        )

    if not part2.exists():
        raise FileNotFoundError(
            f"Split hoàn tất nhưng không tìm thấy part 2:\n{part2}"
        )

    print()
    print("[OK] Đã tạo:")
    print(f"  Part 1: {part1}")
    print(f"  Part 2: {part2}")

    # ============================================================
    # STEP 2: MIGRATE PART 1
    # ============================================================

    run_command(
        [
            sys.executable,
            str(migrate_script),
            str(part1),
        ],
        "STEP 2/3 - THAY AMAZON IMAGE URL TRONG PART 1",
    )

    part1_output = (
        part1.parent
        / f"{part1.stem}_self_hosted.csv"
    )

    if not part1_output.exists():
        raise FileNotFoundError(
            "Migrate part 1 chạy xong nhưng không tìm thấy output:\n"
            f"{part1_output}"
        )

    # ============================================================
    # STEP 3: MIGRATE PART 2
    # ============================================================

    run_command(
        [
            sys.executable,
            str(migrate_script),
            str(part2),
        ],
        "STEP 3/3 - THAY AMAZON IMAGE URL TRONG PART 2",
    )

    part2_output = (
        part2.parent
        / f"{part2.stem}_self_hosted.csv"
    )

    if not part2_output.exists():
        raise FileNotFoundError(
            "Migrate part 2 chạy xong nhưng không tìm thấy output:\n"
            f"{part2_output}"
        )

    # ============================================================
    # DONE
    # ============================================================

    print()
    print("=" * 80)
    print("FLOW COMPLETED SUCCESSFULLY")
    print("=" * 80)

    print()
    print("File cuối cùng để import Shopify:")
    print(f"  1. {part1_output}")
    print(f"  2. {part2_output}")

    print()
    print("File trung gian:")
    print(f"  1. {part1}")
    print(f"  2. {part2}")

    print()
    print(
        "Lưu ý: flow.py chỉ điều phối 2 script. "
        "Logic bảo vệ amazon_link vẫn nằm trong "
        "migrate_rich_description_images.py."
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
