# API giấy phép — hợp đồng cho giai đoạn 7

Máy chủ thử: `http://127.0.0.1:8765`. Online phải dùng HTTPS và tên miền được
khai báo trong `LIVE_STUDIO_TRUSTED_HOSTS`; không đưa cổng thử cục bộ ra Internet.
Giai đoạn 5 chưa cấu hình reverse proxy, TLS hoặc hosting.

## Kích hoạt

`POST /api/license/activate`, Content-Type application/json:

```json
{"key":"KEY_KHACH_DUOC_CAP","device_id":"MA_THIET_BI_ON_DINH_TOI_THIEU_32_KY_TU"}
```

`device_id` gồm 32–256 chữ, số, gạch ngang hoặc gạch dưới. Không dùng tên máy
hoặc thông tin cá nhân làm định danh trực tiếp. Quy tắc tạo fingerprint Windows
ổn định dùng băm MachineGuid Windows; desktop bảo vệ mã kích hoạt bằng DPAPI
theo người dùng Windows và máy hiện tại.

Thành công trả `license` (id, activated_at, expires_at, binding_version),
`activation_token` và `lease`. Lưu mã kích hoạt an toàn trên máy khách.
Kích hoạt lại cùng máy thay thế mã cũ; không tạo lại hạn dùng.

## Kiểm tra định kỳ

`POST /api/license/check`:

```json
{"license_id":"ID_TU_KICH_HOAT","device_id":"CUNG_MA_THIET_BI","activation_token":"MA_KICH_HOAT_DA_LUU"}
```

Thành công trả thông tin hạn dùng và lease mới. Kiểm tra tối đa mỗi 15 phút
hoặc sớm hơn theo `refresh_after`, đồng thời kiểm tra khi mở tool.
Không dùng lại lease offline nếu máy chủ trả từ chối rõ ràng.

Lỗi JSON có dạng `{"error":{"code":"...","message":"..."}}`:

| Mã | HTTP | Cách xử lý dự kiến |
|---|---|---|
| invalid_key / not_found | 404 | Báo key không hợp lệ, không kích hoạt offline |
| device_mismatch | 409 | Báo key thuộc thiết bị khác, liên hệ admin |
| activation_revoked | 409 | Ngừng dùng lease cũ, yêu cầu kích hoạt lại |
| blocked | 403 | Dừng có lưu dữ liệu, không bắt đầu tác vụ mới |
| archived | 403 | Ngừng quyền sử dụng; cần admin khôi phục và mở khóa |
| expired | 410 | Dừng có lưu dữ liệu, yêu cầu gia hạn |
| rate_limited | 429 | Đợi theo Retry-After, không kích hoạt mới offline |
| invalid_input | 400 | Sửa dữ liệu đầu vào |

## Xác minh lease

`GET /api/license/public-key` chỉ công bố public key Ed25519. Khi tích hợp,
**ghim public key đã xác minh trong bản phát hành**, không tải một key tùy ý
từ mạng rồi tin nó. Khóa riêng luôn ở máy chủ.

Lease có dạng `v1.<base64url-json>.<base64url-signature>`. Dữ liệu ký là
`LIVE-STUDIO-LEASE-V1.` cộng phần base64url-json nguyên dạng. Claims gồm
audience, ID key, băm thiết bị, phiên bản liên kết, issued_at, expires_at,
refresh_after và offline_until. Offline_until không quá issued_at + 86400 giây
và không vượt expires_at; không kéo dài hạn dùng bằng khoảng dung sai.

Hàm tham chiếu `license_server.leases.verify_lease` dùng public key để kiểm tra
chữ ký, thiết bị, audience và các mốc thời gian. Desktop đã dùng hàm này, neo
UTC theo thời gian máy chủ đã ký và thời gian đơn điệu; lưu mốc thời gian
mã hóa để kiểm tra khi mở lại. Không chỉ tin đồng hồ Windows có thể bị chỉnh.
Máy chưa từng được cấp lease
đã xác minh không được kích hoạt offline. Không gửi private key, mật khẩu
admin, cookie TikTok, danh sách kênh hoặc video lên/qua API giấy phép.

## Admin và bảo vệ

Mọi `/api/admin/*` yêu cầu phiên admin còn hiệu lực. POST cần header
`X-CSRF-Token` từ phiên cùng nguồn. Phiên hết hiệu lực khi đăng xuất, đổi mật
khẩu hoặc sau 8 giờ; reset mật khẩu cục bộ thu hồi toàn bộ phiên admin.
Không có endpoint tạo/gia hạn/reset key công khai cho máy khách.

Các thao tác bổ sung (đều cần quyền admin):

- POST `/api/admin/licenses/<id>/archive`, `/restore`: chỉ cho key đã từng
  kích hoạt. Khôi phục vẫn giữ khóa; mở khóa bằng thao tác riêng.
- POST `/api/admin/licenses/<id>/delete`: chỉ key chưa từng kích hoạt; giữ
  mã rút gọn trong audit, xóa hàng license trong cùng giao dịch ghi.
- GET `/api/admin/audit/cleanup-preview`: mốc cắt và số bản ghi quá 180 ngày.
- POST `/api/admin/audit/cleanup`, JSON `{"cutoff":TIMESTAMP}`: chỉ dọn trước
  mốc được phép (không mới hơn 180 ngày trước hiện tại), trả số hàng đã xóa.
- GET `/api/admin/audit/export`: tải toàn bộ audit dạng JSON.
- GET `/api/admin/client-config`: tải URL và public key, không chứa bí mật.

Danh sách mặc định ẩn key lưu trữ; lọc `status=archived` để xem. Các API kiểm
tra/kích hoạt từ chối key lưu trữ dù gọi trực tiếp. Xóa và kích hoạt cùng lúc
được tuần tự hóa bằng giao dịch SQLite, không xóa key vừa được kích hoạt.

Tham khảo triển khai: [Flask security](https://flask.palletsprojects.com/en/stable/web-security/),
[Ed25519 trong cryptography](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/),
[Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/usage.html).
