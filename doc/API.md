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

| Field     | Kiểu        | Bắt buộc | Mô tả                                          |
| --------- | ----------- | :------: | ---------------------------------------------- |
| `name`    | text        |    ✅    | Tên khách hàng                                 |
| `email`   | text        |    ✅    | Email                                          |
| `phone`   | text        |    ✅    | Số điện thoại                                  |
| `message` | text        |    ✅    | Yêu cầu ngắn gọn (nội dung textarea)           |
| `file`    | blob (file) |    ❌    | Ảnh hoặc file đính kèm. Bỏ trống nếu không có. |

> **Lưu ý:** Không tự set header `Content-Type` khi gửi bằng `fetch` — để trình
> duyệt tự sinh `boundary`. Giới hạn kích thước file khuyến nghị: **10 MB**
> (khớp `client_max_body_size` của nginx).

### Output — `201 Created`

**Content-Type:** `application/json`

| Field     | Kiểu    | Mô tả                              |
| --------- | ------- | ---------------------------------- |
| `success` | boolean | Luôn `true` khi lưu thành công     |
| `id`      | integer | ID của entry vừa được tạo trong DB |
| `message` | string  | `"Consultation entry saved."`      |

```json
{
  "success": true,
  "id": 1,
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
formData.append("file", fileInput.files[0]); // tùy chọn

const res = await fetch("https://vnote.io.vn/api/consultations", {
  method: "POST",
  body: formData,
});
const data = await res.json(); // { success, id, message }
```

### Ví dụ (curl)

```bash
curl -X POST https://vnote.io.vn/api/consultations \
  -F "name=Nguyen Van A" \
  -F "email=a@example.com" \
  -F "phone=0900000000" \
  -F "message=Toi can tu van san pham X" \
  -F "file=@/path/to/anh.jpg"
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
| Yêu cầu ngắn gọn | `message`          |                                             |
| Tệp đính kèm     | `stored_file_name` | Link tới `/uploads/{...}`, `—` nếu không có |
| Thời gian        | `created_at`       | Định dạng `YYYY-MM-DD HH:MM:SS UTC`         |

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

## Data model — `ConsultationEntry`

Cấu trúc bản ghi lưu trong database (SQLite, bảng `consultation_entries`):

| Field              | Kiểu SQL     | Nullable | Mô tả                                      |
| ------------------ | ------------ | :------: | ------------------------------------------ |
| `id`               | Integer (PK) |    ❌    | Khóa chính, tự tăng                        |
| `name`             | String(255)  |    ❌    | Tên                                        |
| `email`            | String(255)  |    ❌    | Email                                      |
| `phone`            | String(64)   |    ❌    | Điện thoại                                 |
| `message`          | Text         |    ❌    | Yêu cầu ngắn gọn                           |
| `file_name`        | String(512)  |    ✅    | Tên file gốc do customer upload            |
| `stored_file_name` | String(512)  |    ✅    | Tên file lưu trên đĩa (UUID), dùng cho URL |
| `created_at`       | DateTime     |    ❌    | Thời điểm tạo (UTC)                        |

---

## Ghi chú chung

- **CORS:** Server hiện **chưa bật CORS**. Nếu gọi từ frontend khác domain
  (ví dụ trang Shopify `*.myshopify.com` → `vnote.io.vn`), trình duyệt sẽ chặn
  request. Cần thêm `CORSMiddleware` và whitelist domain store.
- **Docs tự động:** FastAPI cung cấp sẵn Swagger UI tại `/docs` và ReDoc tại
  `/redoc` để thử endpoint trực tiếp.
- **Lưu trữ:** Dữ liệu entry nằm ở `data/consultations.db`, file upload nằm ở
  thư mục `uploads/`. Cần backup 2 vị trí này.
