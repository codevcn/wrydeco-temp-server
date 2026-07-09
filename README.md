# Wrydeco Shopify Consultation Server

FastAPI server lưu trữ **Consultation Entry** mà customer gửi từ Shopify store.

## Cấu trúc

```
wrydeco-temp-server/
├── src/
│   ├── __init__.py
│   ├── config.py         # Đường dẫn, cấu hình chung
│   ├── database.py       # Engine + ORM model ConsultationEntry
│   ├── main.py           # FastAPI app + routes
│   └── templates/
│       └── admin.html    # Admin Manager Page
├── data/                 # SQLite DB (tự tạo)
├── uploads/              # File/ảnh customer upload (tự tạo)
├── run.py                # Entry point chạy server
└── requirements.txt
```

## Cài đặt & chạy

```bash
pip install -r requirements.txt
python run.py
```

Server chạy tại `http://localhost:8000`.

## Endpoints

| Method | Route                  | Mô tả                                              |
|--------|------------------------|----------------------------------------------------|
| GET    | `/api/health`          | Healthcheck → `{message, timestamp}`               |
| POST   | `/api/consultations`   | Nhận FormData: `name, email, phone, message, file` |
| GET    | `/admin`               | Admin Manager Page — bảng liệt kê tất cả entry     |
| GET    | `/uploads/{file}`      | Truy cập file customer đã upload                    |

### POST `/api/consultations` — các field FormData

- `name` (text, bắt buộc) — Tên
- `email` (text, bắt buộc) — Email
- `phone` (text, bắt buộc) — Điện thoại
- `message` (text, bắt buộc) — Yêu cầu ngắn gọn
- `file` (blob, tùy chọn) — Ảnh hoặc file đính kèm

Ví dụ gửi từ trình duyệt:

```js
const fd = new FormData();
fd.append("name", "Nguyen Van A");
fd.append("email", "a@example.com");
fd.append("phone", "0900000000");
fd.append("message", "Tôi cần tư vấn sản phẩm X");
fd.append("file", fileInput.files[0]); // tùy chọn

await fetch("http://localhost:8000/api/consultations", {
  method: "POST",
  body: fd,
});
```
