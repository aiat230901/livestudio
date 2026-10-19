# Triển khai admin và máy chủ giấy phép qua HTTPS

Dockerfile tại gốc repo chạy `python -m license_server.hosting`, chỉ chứa máy chủ web. Máy khách tiếp tục ghi video trên Windows. Image này thay cho Dockerfile CLI của dự án gốc; hướng dẫn Docker CLI ở phần README gốc không áp dụng cho image hosting.

## Cấu hình Vibe Host

- Nguồn: repo `aiat230901/livestudio`, nhánh `main`, Dockerfile tại gốc.
- Cổng nội bộ: `3000`; health check: `/health`.
- Trong Settings → Your storage folders, thêm `/app/data`.
- `LIVE_STUDIO_LICENSE_DATA=/app/data`
- `LIVE_STUDIO_TRUSTED_HOSTS=livestudio.n2.tinhgon.xyz` (không thêm giao thức hoặc đường dẫn).
- Giữ HTTPS tại proxy. Máy chủ dùng URL scheme HTTPS để đường dẫn cấu hình máy khách và cookie đúng với địa chỉ công khai.
- Chạy một container cho database SQLite. Không tăng số replica; bản sao lưu SQLite cần được lưu riêng khỏi hosting.

## Chuyển dữ liệu quản trị hiện có

Trên máy quản trị, xuất snapshot nhất quán bằng SQLite backup, không sao chép trực tiếp database đang ghi:

```powershell
.venv/Scripts/python.exe -m license_server.hosting --data-dir .license-server --export-bootstrap .license-server/hosting-bootstrap.txt
```

Tệp này là ZIP mã hóa Base64, **không phải mã hóa bảo mật**. Nó chứa database và khóa ký riêng; chỉ dán vào biến môi trường bí mật `LIVE_STUDIO_BOOTSTRAP_BACKUP` của hosting. Không đưa vào Git, không gửi qua chat, không gửi cho khách hàng. Tệp được tạo mới, không ghi đè tệp đã tồn tại.

Lưu biến, chọn Redeploy từ commit đã sửa Dockerfile. Lần đầu, server khôi phục tài khoản, key và khóa ký vào `/app/data`; thu hồi các phiên đăng nhập admin được chuyển sang. Đăng nhập bằng tài khoản và mật khẩu admin hiện có. Khi database đã có, server không đọc lại backup để tránh ghi đè các thay đổi mới trên hosting.

Sau khi xác nhận đăng nhập và dữ liệu đúng, xóa biến `LIVE_STUDIO_BOOTSTRAP_BACKUP` khỏi cấu hình hosting. Không xóa thư mục `/app/data`. Từ thời điểm chuyển sang, thực hiện quản trị trên hosting để tránh hai database phát sinh thay đổi khác nhau. Snapshot không bao gồm những thay đổi trên máy cục bộ xảy ra sau khi xuất.

Nếu database thiếu `secrets.json`, hoặc backup không đầy đủ, server từ chối khởi động thay vì tự đổi khóa ký. Khôi phục cặp database và secrets từ một bản sao lưu đồng bộ.

## Kiểm tra sau deploy

1. `https://livestudio.n2.tinhgon.xyz/health` trả về `status: ok` và `service: live-studio-license`.
2. Đăng nhập admin và đối chiếu key; tải backup quản trị mới và cất riêng.
3. Tải cấu hình máy khách từ admin; địa chỉ server phải là HTTPS công khai, không phải localhost. Chuyển cấu hình này cho ứng dụng Windows rồi thử kích hoạt, khóa, mở khóa và gia hạn bằng key thử.
4. Redeploy một lần nữa và xác nhận tài khoản, key vẫn còn. Đây là kiểm tra thực tế cơ chế giữ thư mục của hosting.

GitHub Actions “Hosting container” build image Linux, gọi HTTP health/API và khởi động lại container với cùng thư mục dữ liệu. Nó không kiểm tra cơ chế giữ thư mục riêng của Vibe Host; bước 4 vẫn cần thực hiện sau triển khai.
