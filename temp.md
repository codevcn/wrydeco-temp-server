# Ảnh review sản phẩm

## 1. Xóa sản phẩm hiện tại trong khung cảnh tham chiếu

> kèm ảnh khung cảnh tham chiếu.

> kèm ảnh sản phẩm gốc.

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

## 2. Đặt sản phẩm tham chiếu vào khung cảnh tham chiếu

> kèm ảnh khung cảnh tham chiếu.

> kèm ảnh sản phẩm gốc.

```text
Ảnh 1 chứa khung cảnh tham chiếu, ảnh 2 chứa sản phẩm tham chiếu (sản phẩm gốc), tôi dùng {{Google Flow & Nano Banana 2}} để tạo ảnh, bạn hãy viết 1 prompt để yêu cầu {{Nano Banana 2}} tạo 1 ảnh mới đặt sản phẩm trong ảnh 2 vào khung cảnh trong ảnh 1. Yêu cầu cho ảnh kết quả là phải khóa (giữ nguyên) chính xác 100%:
- kết cấu & màu sắc của sản phẩm tham chiếu
- ko được lai (pha trộn) sản phẩm đang ở trong khung cảnh tham chiếu với sản phẩm tham chiếu.
- ánh sáng và các chi tiết vật thể trong khung cảnh tham chiếu
- ko được regenerate lại cả khung cảnh để tránh tạo cảm giác nhìn khung cảnh bị "AI", phải giữ cứng khung cảnh
```

## 3. Tuyệt đối ko thay đổi chi tiết sản phẩm

```text
(tuyệt đối ko được thay đổi bất cứ chi tiết nào về: khung cảnh xung quanh, kết cấu sản phẩm, màu sắc trên toàn bộ sản sản phẩm, ánh sáng trong căn phòng)
```

## 4. Chụp các góc khác nhau của sản phẩm

> kèm ảnh review kết quả đã tạo.

```text
Ảnh đính kèm chứa sản phẩm cần tạo ảnh review, bạn hãy đóng vai một người khách đã mua sản phẩm trong ảnh và đang chụp ảnh sản phẩm để review. Bạn hãy tạo nhiều ảnh review với các góc chụp khác nhau cho sản phẩm trong ảnh đính kèm:

- 1 ảnh chụp cận cảnh một phần sản phẩm (góc máy camera lại sát vào sản phẩm)
- 1 ảnh chụp sản phẩm từ phía xa (góc máy camera nhìn từ xa)
- 1 ảnh chụp sản phẩm từ phía bên trái thẳng hàng với sản phẩm (góc máy camera nhìn từ bên trái)
- 1 ảnh chụp sản phẩm từ phía bên phải thẳng hàng với sản phẩm (góc máy camera nhìn từ bên phải)

(tuyệt đối ko được thay đổi bất cứ chi tiết nào về khung cảnh xung quanh và kết cấu sản phẩm và ánh sáng trong căn phòng)
(QUAN TRỌNG: phải khóa cứng màu sắc của sản phẩm, giữ toàn bộ mọi chi tiết về màu sắc của sản phẩm trong ảnh đính kèm, ko được thay đổi màu sắc sản phẩm)
```

### 4.1. Cho góc máy camera lại gần sản phẩm hơn nữa

```text
tôi muốn góc máy camera sát lại gần sản phẩm hơn nữa (vẫn giữ nguyên chi tiết & kết cấu & màu sắc của sản phẩm, ko được tự ý thay đổi chúng).
```

### 4.2. Tạo các ảnh góc chụp khác nhau từ các ảnh tham chiếu đã học

```text
đây là ảnh các góc chụp khác nhau từ 1 review của 1 trang bán đồ nội thất gỗ. Bạn hãy xem và phân tích chúng.
```

```text
tôi dùng ChatGPT Image 2 để tạo ảnh, bây giờ bạn hãy viết các prompt (các prompt riêng lẻ) để tạo các ảnh góc chụp khác nhau giống như các góc chụp mà bạn đã phân tích được.
```

## 5. Fix prompt khóa cứng sản phẩm

> kèm ảnh review kết quả đã tạo.

```text
Đây là ảnh kết quả, và sản phẩm trong ảnh bị sai kết cấu so với sản phẩm gốc phải ko? Bạn hãy fix lại prompt tạo ảnh của bạn theo hướng khóa cứng sản phẩm đi. Chỉ fix prompt (ko tạo ảnh, ko tạo file, ko tạo video gì hết).
```

## 6. Tách sản phẩm ra 1 nền riêng

> kèm ảnh sản phẩm gốc.

```text
Xác định chủ thể trong ảnh, tách chủ thể ra 1 ảnh riêng có nền trơn màu xám nhạt. Giữ nguyên 100%:
- kết cấu của chủ thể
- màu sắc trên toàn bộ chủ thể

Loại bỏ tất cả các vật thể ko dính liền với chủ thể đi (các vật thể mà chủ thể mang, đựng lên chủ thể), chỉ giữ lại chủ thể.
```

# Bài đăng Blog

## 1. Đọc hiểu bài viết blog

```text
Đọc hiểu bài viết để nắm bối cảnh. Bài viết là 1 blog post về nội thất gỗ.
```

## 2. Đánh giá độ chuyên nghiệp và độ mạnh về SEO từ khóa của bài viết đó

```text
Đánh giá độ chuyên nghiệp trong format trình bày nội dung và độ mạnh về SEO từ khóa của bài viết blog đó.
```
