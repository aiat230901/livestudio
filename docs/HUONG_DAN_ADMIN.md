# Live Studio Admin — bản thử giai đoạn 5

## Mở trang quản trị

Bấm đúp **Mo_Admin.bat** trong thư mục dự án. Cửa sổ máy chủ sẽ mở và trình
duyệt mở địa chỉ **http://127.0.0.1:8765**. Lần đầu, tự chọn tên đăng nhập và
mật khẩu admin (ít nhất 12 ký tự), sau đó đăng nhập. Không có mật khẩu mặc định.

Giữ cửa sổ máy chủ chạy trong lúc dùng trang admin. Đóng trình duyệt không dừng
máy chủ; để dừng, nhấn **Ctrl+C** trong cửa sổ máy chủ. Mở launcher lần nữa sẽ
mở lại địa chỉ của máy chủ đã chạy, không khởi động thêm một bản trên cùng cổng.

Đây là trang dành cho bạn, tách riêng với ứng dụng ghi livestream dành cho
khách. Bản này chạy cục bộ trên máy của bạn. Desktop đã bắt buộc kích hoạt;
hosting HTTPS và đóng gói EXE vẫn là công việc tiếp theo trước khi gửi khách.
Xem [hướng dẫn kích hoạt và kiểm tra](HUONG_DAN_KICH_HOAT.md).

Sau khi cập nhật mã nguồn, dừng máy chủ đang chạy bằng Ctrl+C rồi mở lại
Mo_Admin.bat; tải lại trang trình duyệt. Launcher không tự thay mã của tiến
trình cũ. Cơ sở dữ liệu được nâng cấp giữ nguyên key và tài khoản hiện tại.

## Quản lý key

- **Tạo key mới:** nhập số ngày (1–3650), số lượng (1–100) và ghi chú khách hàng.
  Thời hạn chưa bắt đầu khi tạo key.
- **Lưu key đầy đủ:** sau khi tạo, dùng Sao chép hoặc Tải TXT. Key đầy đủ chỉ
  hiển thị lần này; database chỉ lưu mã băm, danh sách sau đó hiển thị mã rút gọn.
  Nếu làm mất key chưa gửi khách, xóa key chưa kích hoạt đó và tạo key mới.
- **Tìm kiếm/lọc:** tìm theo ghi chú, mã rút gọn hoặc ID; lọc chưa kích hoạt,
  đang hoạt động, hết hạn, đã khóa hoặc đã lưu trữ. Danh sách mặc định ẩn key
  đã lưu trữ; tổng số key vẫn tính cả key lưu trữ. Tìm ghi chú hỗ trợ chữ
  hoa/thường tiếng Việt.
- **Quản lý:** xem ngày kích hoạt/hết hạn, thiết bị, kiểm tra gần nhất và lịch sử.
  Ghi chú sửa được. Các thao tác xóa/lưu trữ có hộp xác nhận.
- **Gia hạn:** key còn hạn được cộng từ ngày hết hạn; key hết hạn được cộng từ
  hiện tại. Key chưa kích hoạt được tăng số ngày của gói, vẫn chưa tính thời hạn.
  Gia hạn không tự mở khóa key đang bị khóa.
- **Khóa/mở khóa:** khóa từ chối lần kích hoạt/kiểm tra giấy phép tiếp theo;
  mở khóa không tự thay đổi hạn dùng.
- **Reset thiết bị:** bỏ liên kết và mã kích hoạt cũ để khách kích hoạt lại.
  Ngày hết hạn vẫn giữ nguyên. Reset không gia hạn key đã hết hạn.
- **Xóa vĩnh viễn:** chỉ dành cho key chưa từng kích hoạt, kể cả key chưa kích
  hoạt đang bị khóa. Key bị xóa không thể kích hoạt hoặc khôi phục. Lịch sử
  giữ mã rút gọn để tra cứu; không lưu key đầy đủ.
- **Lưu trữ:** dành cho key đã từng kích hoạt. Đồng thời khóa quyền sử dụng
  và ẩn khỏi danh sách mặc định, giữ ngày hết hạn và thiết bị.
- **Khôi phục:** chọn bộ lọc Đã lưu trữ, mở Quản lý rồi Khôi phục key. Key vẫn
  ở trạng thái khóa; mở khóa riêng nếu muốn cấp quyền lại, gia hạn nếu đã hết hạn.
- **Đổi mật khẩu:** ở góc trên phải; mọi phiên admin bị đăng xuất sau khi đổi.

Các ngày giờ trên trang dùng giờ Việt Nam UTC+7.

## Quy tắc một thiết bị

Khi kích hoạt lần đầu, máy chủ gắn key với mã thiết bị và bắt đầu thời hạn.
Hai thiết bị kích hoạt cùng lúc chỉ một thiết bị thắng. Kích hoạt lại cùng
thiết bị không đặt lại ngày hết hạn; mã kích hoạt được thay thế bằng mã mới.
Thiết bị khác bị từ chối đến khi bạn reset liên kết.

Giấy phép trả về có chữ ký Ed25519, thời điểm kiểm tra kế tiếp tối đa 15 phút
và hạn dùng offline tối đa 24 giờ từ lần xác thực, không vượt ngày hết hạn.
Máy khách phải ưu tiên kết quả từ chối rõ ràng của máy chủ; không dùng offline
để né key bị khóa/hết hạn/reset. Desktop đã thực hiện các quy tắc này.
Tài khoản admin, khóa ký riêng và database không được đưa vào bản gửi khách.

## Dọn lịch sử

Trong Lịch sử thao tác, **Tải lịch sử JSON** xuất toàn bộ lịch sử hiện có.
**Dọn lịch sử cũ** đếm và hiển thị số bản ghi cũ hơn 180 ngày, kèm mốc thời
gian trước khi xác nhận xóa. Có thể hủy để tải lịch sử trước. Không tự động
dọn và không xóa lịch sử 180 ngày gần nhất. Thao tác dọn được ghi lại.

Việc dọn chỉ xóa lịch sử, không xóa key, liên kết thiết bị hoặc hạn dùng.
SQLite sẽ dùng lại phần dung lượng trống cho dữ liệu mới; kích thước tệp
database không nhất thiết giảm ngay. Chưa cần thao tác nén khóa toàn bộ database
trong lúc máy chủ phục vụ khách.

## Sao lưu và khôi phục

**Sao lưu** tải ZIP có `license.sqlite3`, `secrets.json` và hướng dẫn ngắn.
Đây là bản sao lưu quản trị chứa khóa ký: chỉ giữ riêng, không gửi khách hoặc
đưa vào GitHub. Key đầy đủ đã tạo không thể lấy lại từ bản sao lưu (chỉ có mã băm).

Khôi phục bản thử:

1. Dừng máy chủ cũ bằng Ctrl+C.
2. Giải nén ZIP vào một **thư mục riêng mới**, không ghi đè dữ liệu đang dùng.
3. Chạy lệnh dưới với đường dẫn thư mục vừa giải nén để đăng xuất phiên admin cũ:

   ```powershell
   .venv/Scripts/python.exe -X utf8 -m license_server --data-dir "D:/LiveStudioAdmin-Restore" --revoke-sessions
   ```

4. Mở máy chủ bằng chính thư mục đó:

   ```powershell
   .venv/Scripts/python.exe -X utf8 -m license_server --data-dir "D:/LiveStudioAdmin-Restore" --open
   ```

Không dùng lại Mo_Admin.bat mặc định nếu bạn muốn tiếp tục với thư mục khôi
phục khác; launcher mặc định dùng `.license-server` trong thư mục dự án.
Phải giữ cả database và `secrets.json`; thiếu khóa ký cũ, máy chủ sẽ báo lỗi
thay vì tự tạo khóa mới làm vô hiệu giấy phép đã phát hành.

Nếu quên mật khẩu admin, chạy trực tiếp trên máy chủ:

```powershell
.venv/Scripts/python.exe -X utf8 -m license_server --reset-password TEN_DANG_NHAP
```

Lệnh hỏi mật khẩu mới theo chế độ ẩn; không truyền mật khẩu trong dòng lệnh.
Nếu dùng thư mục riêng, thêm `--data-dir` cùng đường dẫn đang dùng.

## Môi trường phát triển

Bản trên máy hiện tại đã cài thư viện. Với máy phát triển khác:

```powershell
uv sync --frozen --extra dev --extra desktop --extra admin --cache-dir .cache/uv
.venv/Scripts/python.exe -X utf8 -m license_server --open
```

Máy chủ dùng cổng 8765; đổi bằng `--port 8767` nếu cần. Launcher không tự cài
thư viện. Dữ liệu admin mặc định ở `.license-server/`, tách với dữ liệu desktop
tại `%LOCALAPPDATA%/TikTokLiveStudio`.

## Kiểm tra đã thực hiện

Đã kiểm tra dịch vụ, HTTP thật trên máy chủ QA riêng, chữ ký giấy phép,
hai thiết bị kích hoạt đồng thời, hạn dùng, khóa/reset, phiên admin/CSRF,
tải và khôi phục sao lưu. Không dùng mật khẩu/tài khoản của bạn để kiểm tra.

Phiên phát triển không có trình duyệt điều khiển được, nên chưa kiểm tra trực
quan và thao tác JavaScript trong trình duyệt. Bạn có thể mở launcher để dùng
thử và phản hồi giao diện. Kiểm tra hosting/HTTPS và tải thực tế thuộc bước sau.
