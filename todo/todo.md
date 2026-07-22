## Thêm 1 enpoint cho tính năng "Quick Custom Size Request" (Yêu cầu Tùy chỉnh kích thước nhanh)

Tạo 1 endpoint mới để khách hàng có thể gửi yêu cầu tùy chỉnh kích thước sản phẩm nhanh chóng. Endpoint này sẽ nhận dữ liệu từ form (new FormData() của js) trên website và lưu trữ vào cơ sở dữ liệu để đội ngũ sản xuất xử lý.

FormData sẽ bao gồm các trường sau:

- `product_id` (string): ID của sản phẩm mà khách hàng muốn tùy chỉnh
- `product_handle` (string): Handle của sản phẩm
- `product_name` (string): Tên sản phẩm
- `custom_size_description` (string): Mô tả kích thước tùy chỉnh mà khách hàng muốn
- `customer_contact` (string): Email hoặc số điện thoại của khách hàng để liên hệ lại

Server lưu trữ thông tin này vào cơ sở dữ liệu.
