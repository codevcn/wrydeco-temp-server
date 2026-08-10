### 1. Xóa sản phẩm hiện tại trong khung cảnh tham chiếu

> kèm ảnh sản phẩm gốc.

> kèm ảnh tham chiếu khung cảnh.

```text
Ảnh 1 chứa khung cảnh tham chiếu, ảnh 2 chứa sản phẩm tham chiếu (sản phẩm gốc), tôi dùng {{Google Flow & Nano Banana 2}} để tạo ảnh, bạn hãy viết 1 prompt để yêu cầu {{Nano Banana 2}} thực hiện tuần tự các bước sau:
1. Xóa sản phẩm hiện tại trong khung cảnh tham chiếu (ảnh 1)
2. Đặt sản phẩm từ ảnh 2 vào vị trí đã xóa trong khung cảnh tham chiếu (ảnh 1)
Yêu cầu cho ảnh kết quả là phải khóa (giữ nguyên) chính xác 100%:
- kết cấu & màu sắc của sản phẩm tham chiếu
- ko được lai (pha trộn) sản phẩm đang ở trong khung cảnh tham chiếu với sản phẩm tham chiếu.
- ánh sáng và các chi tiết vật thể trong khung cảnh tham chiếu
- ko được regenerate lại cả khung cảnh để tránh tạo cảm giác nhìn khung cảnh bị "AI", phải giữ cứng khung cảnh
```

### 2. Đặt sản phẩm tham chiếu vào khung cảnh tham chiếu

> kèm ảnh sản phẩm gốc.

> kèm ảnh tham chiếu khung cảnh.

```text
Ảnh 1 chứa khung cảnh tham chiếu, ảnh 2 chứa sản phẩm tham chiếu (sản phẩm gốc), tôi dùng {{Google Flow & Nano Banana 2}} để tạo ảnh, bạn hãy viết 1 prompt để yêu cầu {{Nano Banana 2}} tạo 1 ảnh mới đặt sản phẩm trong ảnh 2 vào khung cảnh trong ảnh 1. Yêu cầu cho ảnh kết quả là phải khóa (giữ nguyên) chính xác 100%:
- kết cấu & màu sắc của sản phẩm tham chiếu
- ko được lai (pha trộn) sản phẩm đang ở trong khung cảnh tham chiếu với sản phẩm tham chiếu.
- ánh sáng và các chi tiết vật thể trong khung cảnh tham chiếu
- ko được regenerate lại cả khung cảnh để tránh tạo cảm giác nhìn khung cảnh bị "AI", phải giữ cứng khung cảnh
```

### 3. Tuyệt đối ko thay đổi chi tiết sản phẩm

```text
(tuyệt đối ko được thay đổi bất cứ chi tiết nào về khung cảnh xung quanh và kết cấu sản phẩm và ánh sáng trong căn phòng)
```

### 4. Chụp các góc khác nhau của sản phẩm

> kèm ảnh review kết quả đã tạo.

```text
Ảnh đính kèm chứa sản phẩm cần tạo ảnh review, bạn hãy đóng vai một người khách đã mua sản phẩm trong ảnh và đang chụp ảnh sản phẩm để review. Bạn hãy tạo nhiều ảnh review với các góc chụp khác nhau cho sản phẩm trong ảnh đính kèm.
(tuyệt đối ko được thay đổi bất cứ chi tiết nào về khung cảnh xung quanh và kết cấu sản phẩm và ánh sáng trong căn phòng)
```

### 5. Fix prompt khóa cứng sản phẩm

> kèm ảnh review kết quả đã tạo.

```text
Đây là ảnh kết quả, và sản phẩm trong ảnh bị sai kết cấu so với sản phẩm gốc phải ko? Bạn hãy fix lại prompt tạo ảnh của bạn theo hướng khóa cứng sản phẩm đi. Chỉ fix prompt (ko tạo ảnh, ko tạo file, ko tạo video gì hết).
```