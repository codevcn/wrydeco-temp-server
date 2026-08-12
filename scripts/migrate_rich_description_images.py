import argparse
import csv
import hashlib
import html as html_lib
import json
import os
import re
import tempfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# CONFIG
# ============================================================

UPLOAD_URL = "https://vnote.io.vn/api/upload-image"

RICH_DESCRIPTION_COLUMN = (
    "Rich Description (product.metafields.custom.rich_description)"
)

AMAZON_LINK_COLUMN = "Amazon Link (product.metafields.custom.amazon_link)"

HANDLE_COLUMN = "Handle"

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


# Match Amazon image URLs inside Rich Description only.
#
# Examples currently found in Shopify export:
# https://m.media-amazon.com/...
# https://images-na.ssl-images-amazon.com/...
AMAZON_IMAGE_RE = re.compile(
    r'https?://(?:[^/"\'\s<>]+\.)?'
    r"(?:media-amazon\.com|ssl-images-amazon\.com)"
    r'/[^\s"\'<>]+',
    re.IGNORECASE,
)


CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}


# ============================================================
# HTTP
# ============================================================


def create_session():
    """
    Session dùng retry cho bước DOWNLOAD ảnh Amazon.

    Không tự động retry POST upload để tránh trường hợp:
    server đã lưu ảnh nhưng client bị mất response -> upload trùng.
    """
    session = requests.Session()

    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
    )

    return session


# ============================================================
# CACHE
# ============================================================


def load_cache(cache_path: Path):
    """
    Cache:
        amazon_url -> wrydeco_public_url

    Giúp:
    - không upload cùng ảnh nhiều lần
    - resume nếu script bị dừng giữa chừng
    """
    if not cache_path.exists():
        return {}

    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as exc:
        print(f"[WARNING] Không đọc được cache: {exc}")

    return {}


def save_cache(cache_path: Path, cache: dict):
    temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(temp_path, cache_path)


# ============================================================
# IMAGE DOWNLOAD
# ============================================================


def get_extension_from_response(url: str, content_type: str):
    content_type = content_type.split(";")[0].strip().lower()

    if content_type in CONTENT_TYPE_TO_EXT:
        return CONTENT_TYPE_TO_EXT[content_type]

    # fallback: lấy extension từ URL
    suffix = Path(urlparse(url).path).suffix.lower()

    if suffix in ALLOWED_EXTENSIONS:
        if suffix == ".jpeg":
            return ".jpg"
        return suffix

    raise RuntimeError(
        f"Không xác định được định dạng ảnh.\n"
        f"URL: {url}\n"
        f"Content-Type: {content_type}"
    )


def download_amazon_image(
    session: requests.Session,
    amazon_url: str,
    temp_dir: Path,
):
    """
    Download ảnh Amazon về máy local trước khi upload server.
    """

    # HTML đôi khi chứa &amp;
    request_url = html_lib.unescape(amazon_url)

    print(f"      Download: {request_url}")

    response = session.get(
        request_url,
        stream=True,
        timeout=(15, 90),
        headers={
            "Referer": "https://www.amazon.com/",
        },
    )

    response.raise_for_status()

    content_type = (
        response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    )

    if not content_type.startswith("image/"):
        raise RuntimeError(
            f"Amazon không trả về image.\n"
            f"URL: {request_url}\n"
            f"Content-Type: {content_type}"
        )

    content_length = response.headers.get("Content-Length")

    if content_length:
        try:
            if int(content_length) > MAX_IMAGE_SIZE:
                raise RuntimeError(f"Ảnh lớn hơn 10 MB: {request_url}")
        except ValueError:
            pass

    ext = get_extension_from_response(
        request_url,
        content_type,
    )

    # Filename local ổn định theo URL.
    url_hash = hashlib.sha256(request_url.encode("utf-8")).hexdigest()[:24]

    local_path = temp_dir / f"{url_hash}{ext}"

    downloaded_size = 0

    with local_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue

            downloaded_size += len(chunk)

            if downloaded_size > MAX_IMAGE_SIZE:
                f.close()

                try:
                    local_path.unlink()
                except FileNotFoundError:
                    pass

                raise RuntimeError(f"Ảnh vượt quá giới hạn 10 MB: " f"{request_url}")

            f.write(chunk)

    if downloaded_size == 0:
        raise RuntimeError(f"Download được file rỗng: {request_url}")

    return local_path, content_type


# ============================================================
# UPLOAD TO WRYDECO SERVER
# ============================================================


def upload_to_wrydeco(
    session: requests.Session,
    local_path: Path,
    content_type: str,
):
    """
    POST /api/upload-image

    multipart/form-data:
        image=<file>

    Expected:
        {
            "image_url": "https://vnote.io.vn/uploads/images/..."
        }
    """

    print(f"      Upload  : {local_path.name}")

    with local_path.open("rb") as f:
        response = session.post(
            UPLOAD_URL,
            files={
                "image": (
                    local_path.name,
                    f,
                    content_type,
                )
            },
            timeout=(15, 120),
        )

    if response.status_code != 201:
        raise RuntimeError(
            "Upload Wrydeco thất bại.\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text[:1000]}"
        )

    try:
        data = response.json()
    except Exception:
        raise RuntimeError(
            "Server upload không trả về JSON hợp lệ.\n"
            f"Response: {response.text[:1000]}"
        )

    image_url = data.get("image_url")

    if not image_url:
        raise RuntimeError("Response không có field image_url.\n" f"Response: {data}")

    if not image_url.startswith(("https://", "http://")):
        raise RuntimeError(f"image_url không hợp lệ: {image_url}")

    print(f"      Public  : {image_url}")

    return image_url


# ============================================================
# PROCESS ONE IMAGE
# ============================================================


def migrate_image(
    session: requests.Session,
    amazon_url: str,
    temp_dir: Path,
    cache: dict,
    cache_path: Path,
):
    """
    Amazon URL
        ↓
    kiểm tra cache
        ↓
    download local
        ↓
    upload Wrydeco
        ↓
    public URL
    """

    if amazon_url in cache:
        cached_url = cache[amazon_url]

        if cached_url:
            print(f"      Cached  : {cached_url}")
            return cached_url

    local_path = None

    try:
        local_path, content_type = download_amazon_image(
            session,
            amazon_url,
            temp_dir,
        )

        public_url = upload_to_wrydeco(
            session,
            local_path,
            content_type,
        )

        cache[amazon_url] = public_url

        # Save ngay sau mỗi upload thành công
        # để script có thể resume.
        save_cache(
            cache_path,
            cache,
        )

        return public_url

    finally:
        # Ảnh đã được download thật xuống local,
        # sau khi upload xong thì xóa file tạm.
        if local_path and local_path.exists():
            try:
                local_path.unlink()
            except Exception:
                pass


# ============================================================
# CSV
# ============================================================


def read_csv(csv_path: Path):
    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise RuntimeError("Không đọc được header CSV.")

        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    return fieldnames, rows


def write_csv(
    output_path: Path,
    fieldnames,
    rows,
):
    # Ghi ra file temp trước.
    # Chỉ tạo output chính thức khi hoàn tất.
    temp_output = output_path.with_suffix(output_path.suffix + ".tmp")

    with temp_output.open(
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

    os.replace(
        temp_output,
        output_path,
    )


# ============================================================
# FIND URLS
# ============================================================


def find_amazon_image_urls(value: str):
    if not value:
        return []

    # dict.fromkeys giữ nguyên thứ tự,
    # đồng thời loại URL duplicate trong cùng HTML.
    return list(dict.fromkeys(AMAZON_IMAGE_RE.findall(value)))


# ============================================================
# MAIN PROCESS
# ============================================================


def process_csv(
    input_path: Path,
    output_path: Path,
    cache_path: Path,
):

    fieldnames, rows = read_csv(input_path)

    # --------------------------------------------------------
    # Validate columns
    # --------------------------------------------------------

    required_columns = [
        HANDLE_COLUMN,
        RICH_DESCRIPTION_COLUMN,
        AMAZON_LINK_COLUMN,
    ]

    for column in required_columns:
        if column not in fieldnames:
            raise RuntimeError(f"CSV thiếu column bắt buộc:\n" f"{column}")

    # --------------------------------------------------------
    # HARD LOCK AMAZON LINK
    # --------------------------------------------------------
    #
    # Lưu toàn bộ giá trị amazon_link trước khi xử lý.
    # Sau khi xử lý phải giống 100%.
    #
    amazon_link_before = [row.get(AMAZON_LINK_COLUMN, "") for row in rows]

    # --------------------------------------------------------
    # Group Shopify rows theo Handle
    # --------------------------------------------------------

    products = OrderedDict()

    for row_index, row in enumerate(rows):

        handle = (row.get(HANDLE_COLUMN, "") or "").strip()

        # Shopify export bình thường mỗi row đều có Handle.
        # Nếu có row không Handle vẫn giữ nguyên,
        # nhưng không coi là product mới.
        if not handle:
            continue

        products.setdefault(
            handle,
            [],
        ).append(row_index)

    # --------------------------------------------------------
    # Pre-scan
    # --------------------------------------------------------

    total_occurrences = 0
    unique_urls = set()
    affected_products = set()

    for row in rows:
        rich = (
            row.get(
                RICH_DESCRIPTION_COLUMN,
                "",
            )
            or ""
        )

        urls = AMAZON_IMAGE_RE.findall(rich)

        if urls:
            total_occurrences += len(urls)
            unique_urls.update(urls)

            handle = (row.get(HANDLE_COLUMN, "") or "").strip()

            if handle:
                affected_products.add(handle)

    print("=" * 70)
    print("WRYDECO AMAZON RICH DESCRIPTION IMAGE MIGRATION")
    print("=" * 70)

    print(f"Input             : {input_path}")
    print(f"Output            : {output_path}")
    print(f"Products          : {len(products)}")
    print(f"Affected products : " f"{len(affected_products)}")
    print(f"Amazon occurrences: " f"{total_occurrences}")
    print(f"Unique images     : " f"{len(unique_urls)}")

    print("=" * 70)

    cache = load_cache(cache_path)

    print(f"Cached URLs       : {len(cache)}")

    session = create_session()

    migrated_unique_urls = set()
    changed_products = 0
    changed_cells = 0

    # TemporaryDirectory chính là local storage
    # dùng cho bước download -> upload.
    with tempfile.TemporaryDirectory(
        prefix="wrydeco_amazon_images_"
    ) as temp_dir_string:

        temp_dir = Path(temp_dir_string)

        product_count = len(products)

        for product_number, (
            handle,
            row_indexes,
        ) in enumerate(
            products.items(),
            start=1,
        ):

            product_changed = False

            # Một Shopify product có thể có nhiều row
            # do variant / image.
            for row_index in row_indexes:

                row = rows[row_index]

                original_rich = (
                    row.get(
                        RICH_DESCRIPTION_COLUMN,
                        "",
                    )
                    or ""
                )

                if not original_rich:
                    continue

                amazon_urls = find_amazon_image_urls(original_rich)

                if not amazon_urls:
                    continue

                if not product_changed:
                    print()
                    print(f"[{product_number}/" f"{product_count}] " f"{handle}")

                new_rich = original_rich

                for image_number, amazon_url in enumerate(
                    amazon_urls,
                    start=1,
                ):
                    print(f"   Image " f"{image_number}/" f"{len(amazon_urls)}")

                    public_url = migrate_image(
                        session=session,
                        amazon_url=amazon_url,
                        temp_dir=temp_dir,
                        cache=cache,
                        cache_path=cache_path,
                    )

                    # Chỉ replace bên trong
                    # RICH DESCRIPTION.
                    new_rich = new_rich.replace(
                        amazon_url,
                        public_url,
                    )

                    migrated_unique_urls.add(amazon_url)

                if new_rich != original_rich:
                    row[RICH_DESCRIPTION_COLUMN] = new_rich

                    changed_cells += 1
                    product_changed = True

            if product_changed:
                changed_products += 1

    # ========================================================
    # SAFETY VALIDATION
    # ========================================================

    print()
    print("=" * 70)
    print("VALIDATING")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. Amazon Link metafield MUST NOT CHANGE
    # --------------------------------------------------------

    amazon_link_after = [row.get(AMAZON_LINK_COLUMN, "") for row in rows]

    if amazon_link_before != amazon_link_after:
        raise RuntimeError(
            "\nCRITICAL ERROR:\n"
            "Amazon Link metafield đã bị thay đổi.\n"
            "Output CSV sẽ KHÔNG được tạo."
        )

    print("[OK] amazon_link giữ nguyên 100%.")

    # --------------------------------------------------------
    # 2. Rich Description không được còn Amazon image URL
    # --------------------------------------------------------

    remaining = []

    for row_index, row in enumerate(
        rows,
        start=2,  # header là dòng 1
    ):
        rich = (
            row.get(
                RICH_DESCRIPTION_COLUMN,
                "",
            )
            or ""
        )

        urls = find_amazon_image_urls(rich)

        if urls:
            remaining.append(
                {
                    "csv_row": row_index,
                    "handle": row.get(
                        HANDLE_COLUMN,
                        "",
                    ),
                    "urls": urls,
                }
            )

    if remaining:
        print()
        print("[ERROR] Vẫn còn Amazon image URL " "trong Rich Description:")

        for item in remaining[:10]:
            print(f"Row {item['csv_row']} | " f"{item['handle']}")

            for url in item["urls"]:
                print(f"   {url}")

        raise RuntimeError("Migration chưa hoàn tất. " "Không tạo output CSV.")

    print("[OK] Rich Description không còn " "Amazon image URL.")

    # --------------------------------------------------------
    # 3. Row count
    # --------------------------------------------------------

    print(f"[OK] Tổng row giữ nguyên: {len(rows)}")

    # ========================================================
    # WRITE FINAL CSV
    # ========================================================

    write_csv(
        output_path,
        fieldnames,
        rows,
    )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(f"Products changed   : " f"{changed_products}")

    print(f"Rich Desc cells    : " f"{changed_cells}")

    print(f"Unique URLs moved  : " f"{len(migrated_unique_urls)}")

    print(f"Upload cache       : " f"{cache_path}")

    print(f"Output CSV         : " f"{output_path}")


# ============================================================
# CLI
# ============================================================


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Download Amazon images referenced by Shopify "
            "Rich Description, upload them to Wrydeco server, "
            "then replace only those URLs in Rich Description."
        )
    )

    parser.add_argument(
        "input_csv",
        help="Shopify Products export CSV",
    )

    parser.add_argument(
        "-o",
        "--output",
        help=("Output CSV. Default: " "<input>_self_hosted.csv"),
    )

    parser.add_argument(
        "--cache",
        help=("Upload cache JSON. Default: " "<input>_upload_cache.json"),
    )

    args = parser.parse_args()

    input_path = Path(args.input_csv).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy input CSV: " f"{input_path}")

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = input_path.parent / (input_path.stem + "_self_hosted.csv")

    if args.cache:
        cache_path = Path(args.cache).expanduser().resolve()
    else:
        cache_path = input_path.parent / (input_path.stem + "_upload_cache.json")

    process_csv(
        input_path=input_path,
        output_path=output_path,
        cache_path=cache_path,
    )


if __name__ == "__main__":
    main()
