# Kích hoạt Live Studio — bản thử cục bộ

## Mở và thử

1. Nếu tool đang chạy, chọn **Thoát ứng dụng**, đợi hoàn tất các video đang ghi.
2. Nếu máy chủ admin cũ đang chạy, nhấn **Ctrl+C** trong cửa sổ máy chủ.
3. Mở **Mo_Admin.bat** lại. Tải lại trang admin và đăng nhập bằng tài khoản
   hiện tại; không cần tạo lại tài khoản hoặc xóa dữ liệu.
4. Máy chủ tạo `license-client.json` trong thư mục dự án. Tệp chỉ chứa URL
   máy chủ và khóa công khai để xác minh chữ ký, không chứa tài khoản hay khóa ký riêng.
5. Tạo một key thử, sao chép key đầy đủ ngay khi tạo. Nếu chỉ thử trên máy
   của bạn, hãy dùng key riêng để không chiếm thiết bị của key định gửi khách.
6. Mở **Mo_Tool.bat**, nhập key tại màn hình **Kích hoạt Live Studio**.
7. Sau khi thành công, giao diện ghi livestream mở. Các kênh và lịch đã lưu
   vẫn được giữ. **Cài đặt → Kiểm tra / kích hoạt giấy phép** hiển thị tình trạng
   và thời hạn, đồng thời yêu cầu kiểm tra lại ngay.

Giữ máy chủ chạy trong lúc thử. Một key chỉ gắn một máy Windows; đổi sang máy
khác phải reset thiết bị từ admin rồi kích hoạt lại. Thời hạn tính từ lần đầu
kích hoạt, không tính lại khi mở tool hoặc reset máy.

## Kiểm tra từng chức năng

- **Khóa:** khóa key trong admin. Tool tự kiểm tra tối đa mỗi 15 phút;
  muốn thử ngay, mở Cài đặt và bấm Kiểm tra / kích hoạt giấy phép.
- **Bị từ chối:** tool ngừng theo dõi và gửi lệnh dừng các bản ghi, hoàn tất
  xuất MP4 theo quy trình hiện có. Lịch sử ghi hiển thị Dừng do giấy phép.
  Lỗi ổ đĩa hoặc chuyển đổi vẫn được báo riêng; nguồn thô được giữ theo cơ
  chế phục hồi hiện có. Các kênh, lịch và video đã lưu không bị xóa.
- **Mở khóa/gia hạn:** mở khóa, gia hạn nếu cần, rồi bấm Kiểm tra lại trong
  tool. Các kênh đang bật tiếp tục theo lịch; hạn mức của phiên live vẫn giữ
  nguyên. Lệnh Ghi ngay đã bị hủy khi mất quyền cần bấm lại nếu kênh đang tắt.
- **Lưu trữ/khôi phục:** lưu trữ ngừng quyền; khôi phục vẫn khóa, cần mở khóa
  riêng. Giữ nguyên liên kết máy và ngày hết hạn.
- **Reset thiết bị:** máy cũ bị từ chối lần kiểm tra tiếp theo; nhập lại key
  trên máy muốn sử dụng. Sau khi kích hoạt trên máy khác, máy cũ không dùng được.
- **Mất kết nối máy chủ:** chỉ cho dùng giấy phép có chữ ký đã xác thực trước
  đó, tối đa 24 giờ từ lần xác thực thành công và không vượt ngày hết hạn.
  Thử liên hệ lại mỗi 60 giây. Nếu máy chủ trả rõ ràng là khóa, hết hạn hoặc
  reset thì không chuyển sang offline để tiếp tục dùng.
- **Đồng hồ:** dùng thời gian máy chủ có chữ ký và thời gian trôi trên máy;
  đổi lùi đồng hồ bất thường sẽ yêu cầu xác thực online lại. Hết thời gian
  offline/hết hạn thì dừng, không tự cộng thêm thời gian.

Giấy phép được lưu mã hóa bằng Windows DPAPI tại
`%LOCALAPPDATA%/TikTokLiveStudio/license.dat` (hoặc thư mục `TIKTOK_RECORDER_DATA`
nếu đã thiết lập). Key đầy đủ không được lưu trong tệp này. Không sao chép
tệp kích hoạt giữa người dùng Windows hoặc giữa máy tính.

## Trước khi phân phối cho khách

Bản này vẫn là mã nguồn chạy local. `127.0.0.1` trên máy khách là chính máy
khách, vì vậy chưa thể gửi cấu hình local này cho khách dùng từ xa.

Cần triển khai máy chủ HTTPS, xuất cấu hình công khai từ admin tại
**Hướng dẫn sử dụng → Cấu hình kết nối tool**, rồi đóng gói bản desktop với
địa chỉ và khóa công khai của máy chủ đó. Client từ chối HTTP từ xa, không
tự lấy khóa công khai mới qua mạng khi chữ ký không hợp lệ.

Không đưa `.license-server`, database, khóa ký riêng, tài khoản admin hoặc
bản sao lưu quản trị vào gói khách. Bản desktop đóng gói chỉ cần thành phần
khách và bộ xác minh giấy phép; API Flask/Waitress không cần chạy trên máy khách.

Cấu hình công khai và mã Python của bản thử còn sửa được trên đĩa; bản này
chưa có biện pháp chống sửa/chống can thiệp của bản phát hành. Một thiết bị
là quy tắc liên kết trên máy chủ, không phải cam kết không thể bẻ khóa.
