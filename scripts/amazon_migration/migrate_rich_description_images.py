import argparse
import csv
import hashlib
import html as html_lib
import json
import os
import re
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIG
# ============================================================

SHOPIFY_API_VERSION = "2026-07"
ENV_FILENAME = ".upload.env"

RICH_DESCRIPTION_COLUMN = (
    "Rich Description (product.metafields.custom.rich_description)"
)
AMAZON_LINK_COLUMN = "Amazon Link (product.metafields.custom.amazon_link)"
HANDLE_COLUMN = "Handle"

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_READY_TIMEOUT_SECONDS = 120
FILE_READY_POLL_SECONDS = 2

# Staged upload binary có thể gặp network timeout giữa chừng.
# Mỗi retry tạo một staged target MỚI; fileCreate chỉ chạy sau khi
# binary upload thành công, tránh tạo duplicate file nếu POST upload lỗi.
STAGED_UPLOAD_MAX_ATTEMPTS = 4
STAGED_UPLOAD_CONNECT_TIMEOUT_SECONDS = 60
STAGED_UPLOAD_READ_TIMEOUT_SECONDS = 300
STAGED_UPLOAD_RETRY_BASE_SECONDS = 2
STAGED_UPLOAD_TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}

REQUIRED_ENV_KEYS = (
    "STORE_UPLOAD_DOMAIN",
    "STORE_UPLOAD_CLIENT_ID",
    "STORE_UPLOAD_CLIENT_SECRET",
)
ACCESS_TOKEN_ENV_KEY = "STORE_UPLOAD_ACCESS_TOKEN"

# Match Amazon image URLs inside Rich Description only.
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


def create_download_session():
    """Retry chỉ cho GET ảnh Amazon, không retry các POST tạo asset."""
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
# .upload.env
# ============================================================


def strip_env_value(value: str):
    value = value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]

    return value


def load_env_file(env_path: Path):
    if not env_path.exists():
        raise FileNotFoundError(
            "Không tìm thấy file cấu hình upload:\n"
            f"{env_path}\n\n"
            "Hãy tạo .upload.env cùng cấp với các file Python."
        )

    values = {}

    with env_path.open("r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()

            if not key:
                continue

            values[key] = strip_env_value(value)

    missing = [key for key in REQUIRED_ENV_KEYS if not values.get(key)]

    if missing:
        raise RuntimeError(
            "Thiếu biến bắt buộc trong .upload.env:\n- "
            + "\n- ".join(missing)
        )

    values.setdefault(ACCESS_TOKEN_ENV_KEY, "")
    return values


def update_env_value(env_path: Path, key: str, value: str):
    """Update 1 key nhưng giữ nguyên các dòng/comment khác trong env."""
    lines = []

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()

    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=")
    replaced = False
    output_lines = []

    for line in lines:
        if key_re.match(line):
            output_lines.append(f"{key}={value}")
            replaced = True
        else:
            output_lines.append(line)

    if not replaced:
        output_lines.append(f"{key}={value}")

    temp_path = env_path.with_suffix(env_path.suffix + ".tmp")
    temp_path.write_text(
        "\n".join(output_lines) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, env_path)


def normalize_shop_domain(value: str):
    value = value.strip()

    if not value:
        raise RuntimeError("STORE_UPLOAD_DOMAIN đang trống.")

    if "://" not in value:
        value = "https://" + value

    parsed = urlparse(value)
    domain = (parsed.hostname or "").lower().strip(".")

    if not domain:
        raise RuntimeError(
            f"STORE_UPLOAD_DOMAIN không hợp lệ: {value}"
        )

    if not domain.endswith(".myshopify.com"):
        raise RuntimeError(
            "STORE_UPLOAD_DOMAIN phải là domain Admin API dạng "
            "<shop>.myshopify.com, không phải custom storefront domain.\n"
            f"Giá trị hiện tại: {domain}"
        )

    return domain


# ============================================================
# SHOPIFY ADMIN API / TOKEN
# ============================================================


class ShopifyAdminClient:
    def __init__(self, env_path: Path):
        self.env_path = env_path
        env = load_env_file(env_path)

        self.domain = normalize_shop_domain(env["STORE_UPLOAD_DOMAIN"])
        self.client_id = env["STORE_UPLOAD_CLIENT_ID"]
        self.client_secret = env["STORE_UPLOAD_CLIENT_SECRET"]
        self.access_token = env.get(ACCESS_TOKEN_ENV_KEY, "").strip()
        self.session = requests.Session()

    @property
    def graphql_url(self):
        return (
            f"https://{self.domain}/admin/api/"
            f"{SHOPIFY_API_VERSION}/graphql.json"
        )

    @property
    def token_url(self):
        return f"https://{self.domain}/admin/oauth/access_token"

    def request_new_access_token(self):
        print("      Auth    : requesting new Shopify access token...")

        response = self.session.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=(15, 60),
        )

        if response.status_code >= 400:
            raise RuntimeError(
                "Không lấy được Shopify access token mới.\n"
                f"HTTP: {response.status_code}\n"
                f"Response: {response.text[:1000]}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(
                "Shopify token endpoint không trả JSON hợp lệ.\n"
                f"Response: {response.text[:1000]}"
            ) from exc

        token = (data.get("access_token") or "").strip()

        if not token:
            raise RuntimeError(
                "Shopify token response không có access_token.\n"
                f"Response keys: {sorted(data.keys())}"
            )

        self.access_token = token
        update_env_value(
            self.env_path,
            ACCESS_TOKEN_ENV_KEY,
            token,
        )

        expires_in = data.get("expires_in")
        if expires_in:
            print(f"      Auth    : token refreshed (expires_in={expires_in}s)")
        else:
            print("      Auth    : token refreshed")

        return token

    @staticmethod
    def _looks_like_auth_error(payload):
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if not errors:
            return False

        text = json.dumps(errors, ensure_ascii=False).lower()
        markers = (
            "unauthorized",
            "access token",
            "invalid api key",
            "authentication",
        )
        return any(marker in text for marker in markers)

    def graphql(self, query: str, variables=None, retry_auth=True):
        if not self.access_token:
            self.request_new_access_token()

        response = self.session.post(
            self.graphql_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Shopify-Access-Token": self.access_token,
            },
            json={
                "query": query,
                "variables": variables or {},
            },
            timeout=(15, 120),
        )

        if response.status_code == 401 and retry_auth:
            print("      Auth    : access token rejected/expired; refreshing...")
            self.request_new_access_token()
            return self.graphql(
                query=query,
                variables=variables,
                retry_auth=False,
            )

        if response.status_code >= 400:
            raise RuntimeError(
                "Shopify GraphQL request thất bại.\n"
                f"HTTP: {response.status_code}\n"
                f"Response: {response.text[:1500]}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                "Shopify GraphQL không trả JSON hợp lệ.\n"
                f"Response: {response.text[:1500]}"
            ) from exc

        if self._looks_like_auth_error(payload) and retry_auth:
            print("      Auth    : GraphQL báo auth lỗi; refreshing token...")
            self.request_new_access_token()
            return self.graphql(
                query=query,
                variables=variables,
                retry_auth=False,
            )

        if payload.get("errors"):
            raise RuntimeError(
                "Shopify GraphQL trả top-level errors:\n"
                + json.dumps(
                    payload["errors"],
                    ensure_ascii=False,
                    indent=2,
                )
            )

        return payload.get("data") or {}


# ============================================================
# CACHE
# ============================================================


def load_cache(cache_path: Path):
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


def is_shopify_cdn_url(value: str):
    if not value:
        return False

    try:
        host = (urlparse(value).hostname or "").lower()
    except Exception:
        return False

    return host == "cdn.shopify.com" or host.endswith(".cdn.shopify.com")


# ============================================================
# IMAGE DOWNLOAD
# ============================================================


def get_extension_from_response(url: str, content_type: str):
    content_type = content_type.split(";")[0].strip().lower()

    if content_type in CONTENT_TYPE_TO_EXT:
        return CONTENT_TYPE_TO_EXT[content_type]

    suffix = Path(urlparse(url).path).suffix.lower()

    if suffix in ALLOWED_EXTENSIONS:
        return ".jpg" if suffix == ".jpeg" else suffix

    raise RuntimeError(
        "Không xác định được định dạng ảnh.\n"
        f"URL: {url}\n"
        f"Content-Type: {content_type}"
    )


def download_amazon_image(
    session: requests.Session,
    amazon_url: str,
    temp_dir: Path,
):
    request_url = html_lib.unescape(amazon_url)
    print(f"      Download: {request_url}")

    response = session.get(
        request_url,
        stream=True,
        timeout=(15, 90),
        headers={"Referer": "https://www.amazon.com/"},
    )
    response.raise_for_status()

    content_type = (
        response.headers.get("Content-Type", "")
        .split(";")[0]
        .strip()
        .lower()
    )

    if not content_type.startswith("image/"):
        raise RuntimeError(
            "Amazon không trả về image.\n"
            f"URL: {request_url}\n"
            f"Content-Type: {content_type}"
        )

    content_length = response.headers.get("Content-Length")

    if content_length:
        try:
            if int(content_length) > MAX_IMAGE_SIZE:
                raise RuntimeError(
                    f"Ảnh lớn hơn {MAX_IMAGE_SIZE} bytes: {request_url}"
                )
        except ValueError:
            pass

    ext = get_extension_from_response(request_url, content_type)
    url_hash = hashlib.sha256(
        request_url.encode("utf-8")
    ).hexdigest()[:24]

    # Tên ổn định, dễ nhận biết trong Shopify Content > Files.
    filename = f"amazon-rich-{url_hash}{ext}"
    local_path = temp_dir / filename
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

                raise RuntimeError(
                    f"Ảnh vượt quá giới hạn {MAX_IMAGE_SIZE} bytes: "
                    f"{request_url}"
                )

            f.write(chunk)

    if downloaded_size == 0:
        raise RuntimeError(f"Download được file rỗng: {request_url}")

    return local_path, content_type


# ============================================================
# SHOPIFY CONTENT > FILES UPLOAD
# ============================================================


STAGED_UPLOAD_MUTATION = """
mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets {
      url
      resourceUrl
      parameters {
        name
        value
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

FILE_CREATE_MUTATION = """
mutation fileCreate($files: [FileCreateInput!]!) {
  fileCreate(files: $files) {
    files {
      id
      fileStatus
      ... on MediaImage {
        image {
          url
        }
        fileErrors {
          code
          message
          details
        }
        mediaErrors {
          code
          message
          details
        }
      }
    }
    userErrors {
      code
      field
      message
    }
  }
}
"""

FILE_STATUS_QUERY = """
query fileStatus($id: ID!) {
  node(id: $id) {
    ... on MediaImage {
      id
      fileStatus
      image {
        url
      }
      fileErrors {
        code
        message
        details
      }
      mediaErrors {
        code
        message
        details
      }
    }
  }
}
"""


def format_user_errors(errors):
    return json.dumps(errors or [], ensure_ascii=False, indent=2)


def create_staged_upload(
    shopify: ShopifyAdminClient,
    filename: str,
    content_type: str,
):
    data = shopify.graphql(
        STAGED_UPLOAD_MUTATION,
        {
            "input": [
                {
                    "filename": filename,
                    "mimeType": content_type,
                    "resource": "IMAGE",
                    "httpMethod": "POST",
                }
            ]
        },
    )

    payload = data.get("stagedUploadsCreate") or {}
    errors = payload.get("userErrors") or []

    if errors:
        raise RuntimeError(
            "stagedUploadsCreate thất bại:\n"
            + format_user_errors(errors)
        )

    targets = payload.get("stagedTargets") or []

    if len(targets) != 1:
        raise RuntimeError(
            "stagedUploadsCreate không trả đúng 1 target.\n"
            f"Targets: {len(targets)}"
        )

    target = targets[0]

    if not target.get("url") or not target.get("resourceUrl"):
        raise RuntimeError(
            "Staged upload target thiếu url/resourceUrl."
        )

    return target


class TransientStagedUploadError(RuntimeError):
    """Lỗi network/HTTP tạm thời; an toàn để tạo staged target mới và retry."""


def upload_binary_to_staged_target(
    target: dict,
    local_path: Path,
    content_type: str,
):
    print(f"      Stage   : {local_path.name}")

    form_data = {
        item["name"]: item["value"]
        for item in (target.get("parameters") or [])
    }

    try:
        with local_path.open("rb") as f:
            response = requests.post(
                target["url"],
                data=form_data,
                files={
                    "file": (
                        local_path.name,
                        f,
                        content_type,
                    )
                },
                # Với requests, upload body có thể dùng socket timeout
                # của connect phase. 15s trước đây quá ngắn cho mạng
                # upload chậm; tăng lên 60s và chờ response tối đa 300s.
                timeout=(
                    STAGED_UPLOAD_CONNECT_TIMEOUT_SECONDS,
                    STAGED_UPLOAD_READ_TIMEOUT_SECONDS,
                ),
            )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TransientStagedUploadError(
            "Network timeout/connection error khi upload binary "
            "vào Shopify staged target."
        ) from exc

    if response.status_code in STAGED_UPLOAD_TRANSIENT_HTTP:
        raise TransientStagedUploadError(
            "Shopify staged target trả lỗi HTTP tạm thời.\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text[:1500]}"
        )

    if response.status_code >= 400:
        raise RuntimeError(
            "Upload binary vào Shopify staged target thất bại.\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text[:1500]}"
        )


def create_shopify_file(
    shopify: ShopifyAdminClient,
    resource_url: str,
    filename: str,
):
    data = shopify.graphql(
        FILE_CREATE_MUTATION,
        {
            "files": [
                {
                    "contentType": "IMAGE",
                    "originalSource": resource_url,
                    "filename": filename,
                    "duplicateResolutionMode": "APPEND_UUID",
                }
            ]
        },
    )

    payload = data.get("fileCreate") or {}
    errors = payload.get("userErrors") or []

    if errors:
        raise RuntimeError(
            "fileCreate thất bại:\n"
            + format_user_errors(errors)
        )

    files = payload.get("files") or []

    if len(files) != 1 or not files[0].get("id"):
        raise RuntimeError(
            "fileCreate không trả đúng 1 file hợp lệ.\n"
            f"Response: {json.dumps(payload, ensure_ascii=False)[:1500]}"
        )

    return files[0]


def extract_processing_errors(file_node: dict):
    errors = []

    for key in ("fileErrors", "mediaErrors"):
        for item in file_node.get(key) or []:
            errors.append(
                {
                    "type": key,
                    "code": item.get("code"),
                    "message": item.get("message"),
                    "details": item.get("details"),
                }
            )

    return errors


def wait_for_shopify_file_ready(
    shopify: ShopifyAdminClient,
    file_id: str,
):
    deadline = time.monotonic() + FILE_READY_TIMEOUT_SECONDS
    last_status = None

    while time.monotonic() < deadline:
        data = shopify.graphql(
            FILE_STATUS_QUERY,
            {"id": file_id},
        )

        node = data.get("node")

        if not node:
            raise RuntimeError(
                f"Không đọc được Shopify file sau fileCreate: {file_id}"
            )

        status = node.get("fileStatus")

        if status != last_status:
            print(f"      Status  : {status}")
            last_status = status

        if status == "FAILED":
            raise RuntimeError(
                "Shopify xử lý image thất bại:\n"
                + json.dumps(
                    extract_processing_errors(node),
                    ensure_ascii=False,
                    indent=2,
                )
            )

        image = node.get("image") or {}
        public_url = image.get("url")

        if status == "READY" and public_url:
            if not public_url.startswith(("https://", "http://")):
                raise RuntimeError(
                    f"Shopify trả CDN URL không hợp lệ: {public_url}"
                )

            return public_url

        time.sleep(FILE_READY_POLL_SECONDS)

    raise TimeoutError(
        "Hết thời gian chờ Shopify xử lý image.\n"
        f"File ID: {file_id}\n"
        f"Timeout: {FILE_READY_TIMEOUT_SECONDS}s"
    )


def upload_to_shopify_files(
    shopify: ShopifyAdminClient,
    local_path: Path,
    content_type: str,
):
    # Chỉ retry phase staged-upload TRƯỚC fileCreate.
    # Nếu binary POST timeout, không thể chắc server đã nhận hết body hay chưa,
    # nên không reuse target cũ: tạo target mới rồi upload lại. Vì fileCreate
    # chưa được gọi nên retry kiểu này không tạo duplicate ở Content > Files.
    target = None
    last_error = None

    for attempt in range(1, STAGED_UPLOAD_MAX_ATTEMPTS + 1):
        if attempt > 1:
            delay = STAGED_UPLOAD_RETRY_BASE_SECONDS * (2 ** (attempt - 2))
            print(
                f"      Retry   : staged upload attempt "
                f"{attempt}/{STAGED_UPLOAD_MAX_ATTEMPTS} after {delay}s"
            )
            time.sleep(delay)

        target = create_staged_upload(
            shopify=shopify,
            filename=local_path.name,
            content_type=content_type,
        )

        try:
            upload_binary_to_staged_target(
                target=target,
                local_path=local_path,
                content_type=content_type,
            )
            last_error = None
            break
        except TransientStagedUploadError as exc:
            last_error = exc
            print(
                "      Warning : staged binary upload lỗi tạm thời; "
                "sẽ tạo target mới và thử lại."
            )

    if last_error is not None:
        raise RuntimeError(
            "Upload binary lên Shopify thất bại sau "
            f"{STAGED_UPLOAD_MAX_ATTEMPTS} lần thử.\n"
            f"Lỗi cuối: {last_error}"
        ) from last_error

    created = create_shopify_file(
        shopify=shopify,
        resource_url=target["resourceUrl"],
        filename=local_path.name,
    )

    initial_status = created.get("fileStatus")
    initial_image = created.get("image") or {}
    initial_url = initial_image.get("url")

    if initial_status == "FAILED":
        raise RuntimeError(
            "Shopify fileCreate trả FAILED:\n"
            + json.dumps(
                extract_processing_errors(created),
                ensure_ascii=False,
                indent=2,
            )
        )

    if initial_status == "READY" and initial_url:
        public_url = initial_url
    else:
        public_url = wait_for_shopify_file_ready(
            shopify=shopify,
            file_id=created["id"],
        )

    print(f"      CDN     : {public_url}")
    return public_url


# ============================================================
# PROCESS ONE IMAGE
# ============================================================


def migrate_image(
    download_session: requests.Session,
    shopify: ShopifyAdminClient,
    amazon_url: str,
    temp_dir: Path,
    cache: dict,
    cache_path: Path,
):
    cached_url = cache.get(amazon_url)

    if cached_url and is_shopify_cdn_url(cached_url):
        print(f"      Cached  : {cached_url}")
        return cached_url

    if cached_url:
        print(
            "      Cache   : bỏ qua URL cache cũ không thuộc Shopify CDN"
        )

    local_path = None

    try:
        local_path, content_type = download_amazon_image(
            download_session,
            amazon_url,
            temp_dir,
        )

        public_url = upload_to_shopify_files(
            shopify=shopify,
            local_path=local_path,
            content_type=content_type,
        )

        cache[amazon_url] = public_url
        save_cache(cache_path, cache)
        return public_url

    finally:
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


def write_csv(output_path: Path, fieldnames, rows):
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

    os.replace(temp_output, output_path)


def find_amazon_image_urls(value: str):
    if not value:
        return []

    return list(dict.fromkeys(AMAZON_IMAGE_RE.findall(value)))


# ============================================================
# MAIN PROCESS
# ============================================================


def process_csv(
    input_path: Path,
    output_path: Path,
    cache_path: Path,
    env_path: Path,
):
    fieldnames, rows = read_csv(input_path)

    required_columns = [
        HANDLE_COLUMN,
        RICH_DESCRIPTION_COLUMN,
        AMAZON_LINK_COLUMN,
    ]

    for column in required_columns:
        if column not in fieldnames:
            raise RuntimeError(f"CSV thiếu column bắt buộc:\n{column}")

    # HARD LOCK amazon_link
    amazon_link_before = [
        row.get(AMAZON_LINK_COLUMN, "")
        for row in rows
    ]

    products = OrderedDict()

    for row_index, row in enumerate(rows):
        handle = (row.get(HANDLE_COLUMN, "") or "").strip()
        if not handle:
            continue
        products.setdefault(handle, []).append(row_index)

    total_occurrences = 0
    unique_urls = set()
    affected_products = set()

    for row in rows:
        rich = row.get(RICH_DESCRIPTION_COLUMN, "") or ""
        urls = AMAZON_IMAGE_RE.findall(rich)

        if urls:
            total_occurrences += len(urls)
            unique_urls.update(urls)

            handle = (row.get(HANDLE_COLUMN, "") or "").strip()
            if handle:
                affected_products.add(handle)

    print("=" * 70)
    print("SHOPIFY CONTENT > FILES IMAGE MIGRATION")
    print("=" * 70)
    print(f"Input             : {input_path}")
    print(f"Output            : {output_path}")
    print(f"Env               : {env_path}")
    print(f"Products          : {len(products)}")
    print(f"Affected products : {len(affected_products)}")
    print(f"Amazon occurrences: {total_occurrences}")
    print(f"Unique images     : {len(unique_urls)}")
    print("=" * 70)

    cache = load_cache(cache_path)
    print(f"Cached URLs       : {len(cache)}")

    # Chỉ cần auth Shopify nếu thực sự có ảnh cần migrate.
    shopify = None
    if unique_urls:
        shopify = ShopifyAdminClient(env_path)
        print(f"Shop              : {shopify.domain}")
        print(f"Admin API         : {SHOPIFY_API_VERSION}")

    download_session = create_download_session()
    migrated_unique_urls = set()
    changed_products = 0
    changed_cells = 0

    with tempfile.TemporaryDirectory(
        prefix="wrydeco_amazon_images_"
    ) as temp_dir_string:
        temp_dir = Path(temp_dir_string)
        product_count = len(products)

        for product_number, (handle, row_indexes) in enumerate(
            products.items(),
            start=1,
        ):
            product_changed = False

            for row_index in row_indexes:
                row = rows[row_index]
                original_rich = row.get(RICH_DESCRIPTION_COLUMN, "") or ""

                if not original_rich:
                    continue

                amazon_urls = find_amazon_image_urls(original_rich)

                if not amazon_urls:
                    continue

                if not product_changed:
                    print()
                    print(f"[{product_number}/{product_count}] {handle}")

                new_rich = original_rich

                for image_number, amazon_url in enumerate(
                    amazon_urls,
                    start=1,
                ):
                    print(
                        f"   Image {image_number}/{len(amazon_urls)}"
                    )

                    public_url = migrate_image(
                        download_session=download_session,
                        shopify=shopify,
                        amazon_url=amazon_url,
                        temp_dir=temp_dir,
                        cache=cache,
                        cache_path=cache_path,
                    )

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

    amazon_link_after = [
        row.get(AMAZON_LINK_COLUMN, "")
        for row in rows
    ]

    if amazon_link_before != amazon_link_after:
        raise RuntimeError(
            "\nCRITICAL ERROR:\n"
            "Amazon Link metafield đã bị thay đổi.\n"
            "Output CSV sẽ KHÔNG được tạo."
        )

    print("[OK] amazon_link giữ nguyên 100%.")

    remaining = []

    for row_index, row in enumerate(rows, start=2):
        rich = row.get(RICH_DESCRIPTION_COLUMN, "") or ""
        urls = find_amazon_image_urls(rich)

        if urls:
            remaining.append(
                {
                    "csv_row": row_index,
                    "handle": row.get(HANDLE_COLUMN, ""),
                    "urls": urls,
                }
            )

    if remaining:
        print("[ERROR] Vẫn còn Amazon image URL trong Rich Description:")

        for item in remaining[:10]:
            print(f"Row {item['csv_row']} | {item['handle']}")
            for url in item["urls"]:
                print(f"   {url}")

        raise RuntimeError(
            "Migration chưa hoàn tất. Không tạo output CSV."
        )

    print("[OK] Rich Description không còn Amazon image URL.")
    print(f"[OK] Tổng row giữ nguyên: {len(rows)}")

    # Thêm validation: mọi URL vừa migrate phải là Shopify CDN.
    bad_cached_targets = [
        (source, target)
        for source, target in cache.items()
        if source in migrated_unique_urls and not is_shopify_cdn_url(target)
    ]

    if bad_cached_targets:
        raise RuntimeError(
            "CRITICAL ERROR: Có URL migrate không thuộc Shopify CDN."
        )

    print("[OK] URL mới thuộc Shopify CDN.")

    write_csv(output_path, fieldnames, rows)

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"Products changed   : {changed_products}")
    print(f"Rich Desc cells    : {changed_cells}")
    print(f"Unique URLs moved  : {len(migrated_unique_urls)}")
    print(f"Upload cache       : {cache_path}")
    print(f"Output CSV         : {output_path}")


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Download Amazon images trong Shopify Rich Description, "
            "upload vào Shopify Content > Files, chờ Shopify CDN READY, "
            "rồi replace chỉ các URL đó trong Rich Description."
        )
    )

    parser.add_argument(
        "input_csv",
        help="Shopify Products export CSV",
    )

    parser.add_argument(
        "-o",
        "--output",
        help=(
            "Output CSV. Default: <input>_shopify_files.csv"
        ),
    )

    parser.add_argument(
        "--cache",
        help=(
            "Upload cache JSON. Default: "
            "<input>_shopify_upload_cache.json"
        ),
    )

    parser.add_argument(
        "--env",
        dest="env_path",
        help=(
            "Path tới .upload.env. Default: .upload.env cùng cấp script"
        ),
    )

    args = parser.parse_args()
    input_path = Path(args.input_csv).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy input CSV: {input_path}")

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = (
            input_path.parent
            / f"{input_path.stem}_shopify_files.csv"
        )

    if args.cache:
        cache_path = Path(args.cache).expanduser().resolve()
    else:
        cache_path = (
            input_path.parent
            / f"{input_path.stem}_shopify_upload_cache.json"
        )

    if args.env_path:
        env_path = Path(args.env_path).expanduser().resolve()
    else:
        env_path = Path(__file__).resolve().parent / ENV_FILENAME

    process_csv(
        input_path=input_path,
        output_path=output_path,
        cache_path=cache_path,
        env_path=env_path,
    )


if __name__ == "__main__":
    main()
