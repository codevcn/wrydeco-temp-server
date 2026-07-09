# API Documentation — Wrydeco Shopify Consultation Server

Tài liệu mô tả chi tiết toàn bộ endpoint của server FastAPI lưu trữ **Consultation Entry**.

- **Base URL (production):** `https://vnote.io.vn`
- **Base URL (local/dev):** `http://localhost:8000`
- **Định dạng dữ liệu:** JSON (trừ endpoint upload dùng `multipart/form-data`)
- **Timestamp:** ISO 8601, múi giờ UTC (ví dụ `2026-07-09T11:54:53.182226+00:00`)

## Tổng quan các endpoint

| #   | Method | Route                         | Chức năng                                | Kiểu response |
| --- | ------ | ----------------------------- | ---------------------------------------- | ------------- |
| 1   | `GET`  | `/api/health`                 | Healthcheck                              | JSON          |
| 2   | `POST` | `/api/consultations`          | Nhận & lưu 1 consultation entry          | JSON          |
| 3   | `GET`  | `/admin`                      | Trang HTML quản trị (bảng liệt kê entry) | HTML          |
| 4   | `GET`  | `/uploads/{stored_file_name}` | Tải/xem file customer đã upload          | File (binary) |

---

## 1. `GET /api/health`

Kiểm tra server còn sống. Không cần tham số.

### Input

_Không có._

### Output — `200 OK`

**Content-Type:** `application/json`

| Field       | Kiểu   | Mô tả                                         |
| ----------- | ------ | --------------------------------------------- |
| `message`   | string | Luôn là `"Shopify Server responses Hello!!!"` |
| `timestamp` | string | Thời điểm hiện tại (ISO 8601, UTC)            |

```json
{
  "message": "Shopify Server responses Hello!!!",
  "timestamp": "2026-07-09T11:54:53.182226+00:00"
}
```

### Ví dụ

```bash
curl https://vnote.io.vn/api/health
```

---

## 2. `POST /api/consultations`

Nhận 1 `FormData` gửi từ trình duyệt và lưu vào database. File đính kèm (nếu có)
được lưu lên đĩa với tên duy nhất (UUID).

### Input

**Content-Type:** `multipart/form-data`

| Field     | Kiểu               | Bắt buộc | Mô tả                                                          |
| --------- | ------------------ | :------: | -------------------------------------------------------------- |
| `name`    | text               |    ✅    | Tên khách hàng                                                 |
| `email`   | text               |    ✅    | Email                                                          |
| `phone`   | text               |    ✅    | Số điện thoại                                                  |
| `message` | text               |    ✅    | Yêu cầu ngắn gọn (nội dung textarea)                           |
| `files`   | blob[] (nhiều file) |    ❌    | Ảnh/file đính kèm. **Nhiều file**: lặp lại field `files` nhiều lần. Bỏ trống nếu không có. |

> **Lưu ý:**
> - Field tên là `files` (số nhiều). Để gửi nhiều file, `append("files", ...)`
>   nhiều lần với cùng tên `files`.
> - Không tự set header `Content-Type` khi gửi bằng `fetch` — để trình duyệt tự
>   sinh `boundary`. Giới hạn kích thước mỗi request khuyến nghị: **10 MB**
>   (khớp `client_max_body_size` của nginx).

### Output — `201 Created`

**Content-Type:** `application/json`

| Field        | Kiểu    | Mô tả                                       |
| ------------ | ------- | ------------------------------------------- |
| `success`    | boolean | Luôn `true` khi lưu thành công              |
| `id`         | integer | ID của entry vừa được tạo trong DB          |
| `file_count` | integer | Số file đã lưu kèm entry (0 nếu không gửi)  |
| `message`    | string  | `"Consultation entry saved."`               |

```json
{
  "success": true,
  "id": 1,
  "file_count": 2,
  "message": "Consultation entry saved."
}
```

### Output lỗi — `422 Unprocessable Entity`

Trả về khi thiếu field bắt buộc (`name`, `email`, `phone`, hoặc `message`).
Đây là format lỗi validation mặc định của FastAPI.

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "email"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

### Ví dụ (JavaScript / fetch)

```javascript
const formData = new FormData();
formData.append("name", "Nguyen Van A");
formData.append("email", "a@example.com");
formData.append("phone", "0900000000");
formData.append("message", "Tôi cần tư vấn sản phẩm X");

// Gửi nhiều file: append cùng tên "files" nhiều lần
for (const file of fileInput.files) {
  formData.append("files", file);
}

const res = await fetch("https://vnote.io.vn/api/consultations", {
  method: "POST",
  body: formData,
});
const data = await res.json(); // { success, id, file_count, message }
```

### Ví dụ (curl)

```bash
curl -X POST https://vnote.io.vn/api/consultations \
  -F "name=Nguyen Van A" \
  -F "email=a@example.com" \
  -F "phone=0900000000" \
  -F "message=Toi can tu van san pham X" \
  -F "files=@/path/to/anh1.jpg" \
  -F "files=@/path/to/anh2.png"
```

---

## 3. `GET /admin`

Trả về **Admin Manager Page** — trang HTML có tiêu đề `"Admin Manager Page"`,
main section là 1 bảng liệt kê **tất cả** consultation entry đã lưu, sắp xếp theo
thời gian tạo giảm dần (mới nhất lên đầu).

### Input

_Không có tham số._

### Output — `200 OK`

**Content-Type:** `text/html; charset=utf-8`

Trả về HTML render sẵn. Bảng gồm các cột:

| Cột              | Nguồn dữ liệu      | Mô tả                                       |
| ---------------- | ------------------ | ------------------------------------------- |
| ID               | `id`               | Khóa chính                                  |
| Tên              | `name`             |                                             |
| Email            | `email`            |                                             |
| Điện thoại       | `phone`            |                                             |
| Yêu cầu ngắn gọn | `message`          |                                                            |
| Tệp đính kèm     | `files[]`          | Danh sách link tới `/uploads/{...}` (mỗi file 1 dòng), `—` nếu không có |
| Thời gian        | `created_at`       | Định dạng `YYYY-MM-DD HH:MM:SS UTC`                        |

Khi chưa có entry nào, bảng hiển thị dòng: _"Chưa có consultation entry nào được lưu."_

### Ví dụ

Mở trực tiếp trên trình duyệt: `https://vnote.io.vn/admin`

---

## 4. `GET /uploads/{stored_file_name}`

Phục vụ (serve) file mà customer đã upload. Route này được mount qua
`StaticFiles`; link trong trang `/admin` trỏ tới đây.

### Input

| Tham số            | Vị trí | Kiểu   | Mô tả                                                   |
| ------------------ | ------ | ------ | ------------------------------------------------------- |
| `stored_file_name` | path   | string | Tên file đã lưu trên đĩa (dạng UUID + phần mở rộng gốc) |

### Output

- **`200 OK`** — trả về nội dung file (binary). `Content-Type` được suy ra từ
  phần mở rộng của file (ví dụ `image/jpeg`, `application/pdf`).
- **`404 Not Found`** — nếu file không tồn tại.

### Ví dụ

```
https://vnote.io.vn/uploads/3f2a9c8b1d4e4f7a9b0c1d2e3f4a5b6c.jpg
```

---

## Data model

Quan hệ **1 entry — nhiều file** (1-to-many).

### Bảng `consultation_entries` — `ConsultationEntry`

| Field        | Kiểu SQL     | Nullable | Mô tả                          |
| ------------ | ------------ | :------: | ------------------------------ |
| `id`         | Integer (PK) |    ❌    | Khóa chính, tự tăng            |
| `name`       | String(255)  |    ❌    | Tên                            |
| `email`      | String(255)  |    ❌    | Email                          |
| `phone`      | String(64)   |    ❌    | Điện thoại                     |
| `message`    | Text         |    ❌    | Yêu cầu ngắn gọn               |
| `created_at` | DateTime     |    ❌    | Thời điểm tạo (UTC)            |
| `files`      | relationship |    —     | Danh sách `ConsultationFile`   |

### Bảng `consultation_files` — `ConsultationFile`

| Field              | Kiểu SQL              | Nullable | Mô tả                                      |
| ------------------ | --------------------- | :------: | ------------------------------------------ |
| `id`               | Integer (PK)          |    ❌    | Khóa chính, tự tăng                        |
| `entry_id`         | Integer (FK)          |    ❌    | Trỏ tới `consultation_entries.id`          |
| `file_name`        | String(512)           |    ❌    | Tên file gốc do customer upload            |
| `stored_file_name` | String(512)           |    ❌    | Tên file lưu trên đĩa (UUID), dùng cho URL |

---

## Cách restart server đúng cách sau khi pull code mới về

Server FastAPI hiện đang chạy nền bằng `systemd` service:

```txt
wrydeco-temp-server.service
```

Không nên chạy lại server thủ công bằng:

```bash
python run.py
```

vì cách đó sẽ giữ terminal và không phù hợp cho production.

---

### 1. SSH vào VPS

```bash
ssh vmadmin@160.25.81.57
```

---

### 2. Đi vào thư mục project

```bash
cd /var/www/wrydeco-temp-server
```

---

### 3. Pull code mới nhất

```bash
git pull origin main
```

---

### 4. Đảm bảo quyền file đúng user deploy

```bash
sudo chown -R vmadmin:vmadmin /var/www/wrydeco-temp-server
```

---

### 5. Cài lại dependencies nếu có thay đổi `requirements.txt`

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 6. Restart FastAPI service

```bash
sudo systemctl restart wrydeco-temp-server
```

---

### 7. Kiểm tra trạng thái service

```bash
sudo systemctl status wrydeco-temp-server
```

Kết quả đúng cần thấy:

```txt
Active: active (running)
```

---

### 8. Test server nội bộ trên VPS

```bash
curl http://127.0.0.1:8000/admin
```

Nếu route `/admin` hoạt động, server sẽ trả về HTML admin page.

---

### 9. Test domain public HTTPS

```bash
curl -i https://vnote.io.vn/admin
```

Kết quả đúng cần có HTTP status `200 OK`.

---

### 10. Xem log nếu restart bị lỗi

Xem 100 dòng log gần nhất:

```bash
sudo journalctl -u wrydeco-temp-server -n 100 --no-pager
```

Xem log realtime:

```bash
sudo journalctl -u wrydeco-temp-server -f
```

Thoát log realtime:

```txt
Ctrl + C
```

---

### 11. Khi nào cần reload Nginx?

Chỉ cần reload Nginx nếu có sửa config Nginx, ví dụ file:

```txt
/etc/nginx/sites-available/vnote.io.vn
```

Khi đó chạy:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Nếu chỉ pull code FastAPI mới thì không cần reload Nginx.

---

## Lệnh rút gọn thường dùng

Sau khi đã pull code về, thường chỉ cần chạy:

```bash
cd /var/www/wrydeco-temp-server
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart wrydeco-temp-server
sudo systemctl status wrydeco-temp-server
```

---

## Ghi nhớ

Luồng production hiện tại là:

```txt
https://vnote.io.vn
        ↓
Nginx Reverse Proxy
        ↓
http://127.0.0.1:8000
        ↓
FastAPI / Uvicorn
        ↓
systemd service: wrydeco-temp-server
```

Vì vậy, cách restart đúng là restart service:

```bash
sudo systemctl restart wrydeco-temp-server
```

---

## Ghi chú chung

- **CORS:** Server hiện **chưa bật CORS**. Nếu gọi từ frontend khác domain
  (ví dụ trang Shopify `*.myshopify.com` → `vnote.io.vn`), trình duyệt sẽ chặn
  request. Cần thêm `CORSMiddleware` và whitelist domain store.
- **Docs tự động:** FastAPI cung cấp sẵn Swagger UI tại `/docs` và ReDoc tại
  `/redoc` để thử endpoint trực tiếp.
- **Lưu trữ:** Dữ liệu entry nằm ở `data/consultations.db`, file upload nằm ở
  thư mục `uploads/`. Cần backup 2 vị trí này.
