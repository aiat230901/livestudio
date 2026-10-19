# Bản Windows và quy trình cập nhật

## Bản tải về

Gói `LiveStudio-1.0.0-Windows-x64.zip` chứa một thư mục `LiveStudio`. Giải nén toàn bộ rồi mở `LiveStudio.exe`. Python, Qt, FFmpeg và FFprobe đã nằm trong gói; không cần cài chúng trên máy khách. Mục tiêu là Windows 10/11 x64; kiểm tra chạy thực tế hiện thực hiện trên Windows 11 của máy phát triển.

Ứng dụng dùng địa chỉ HTTPS công khai và khóa kiểm tra giấy phép được đóng gói. Thay `license-client.json` bên ngoài không đổi được cấu hình bản EXE. Mã nguồn vẫn là Python được đóng gói, không được coi là cơ chế chống dịch ngược tuyệt đối.

Giữ video ngoài thư mục chương trình. Kênh, lịch, thiết lập và cache giấy phép nằm ở `%LOCALAPPDATA%/TikTokLiveStudio`; `application.log` cũng ở đó. Nếu phát hiện tệp riêng/video được thêm trong thư mục tool, cập nhật sẽ yêu cầu chuyển chúng ra ngoài trước khi thay thư mục. Thư mục bản cũ luôn được giữ với hậu tố `.previous-...`.

## Một lần cấu hình trên Vibe Host

1. Thêm biến `LIVE_STUDIO_UPDATE_PUBLIC_KEY` bằng nội dung `.release-signing/update-public-key.txt`. Đây là khóa công khai, không phải `update-signing.key`.
2. Giữ `/app/data` trong Your storage folders; giữ hai biến `LIVE_STUDIO_LICENSE_DATA` và `LIVE_STUDIO_TRUSTED_HOSTS` trước đó.
3. Sau khi đã xác nhận dữ liệu chuyển lên đúng và còn qua lần Redeploy tiếp theo, xóa biến `LIVE_STUDIO_BOOTSTRAP_BACKUP`. Không xóa `/app/data`.
4. Redeploy nhánh `main` sau khi source mới được đẩy lên. Kiểm tra `/health` có `api_revision: 3`.
5. Đăng nhập admin, mở **Bản phát hành**. Chọn ZIP và JSON cùng phiên bản, bấm **Phát hành bản mới**. Không đóng trang khi đang tải. Mỗi yêu cầu chỉ tải tối đa 256 KiB; hosting chỉ công bố sau khi đủ gói và mã SHA-256 đúng. Nếu mạng ngắt, tải lại từ đầu; bản đã phát hành được giữ.

ZIP có thể được tải công khai qua liên kết trên trang Bản phát hành. Gửi liên kết hoặc ZIP này cho khách cùng key riêng. Gói không có thông tin admin hoặc khóa ký riêng. Repo source GitHub vẫn private và không chứa các bản ZIP lớn.

## Những lần cập nhật sau

1. Chỉnh source, kiểm tra chức năng và test. Chọn phiên bản tăng dần theo dạng `1.0.1`, `1.0.2`, `1.1.0`.
2. Trên máy quản trị có khóa ký, đồng bộ môi trường rồi chạy:

```powershell
uv sync --frozen --extra desktop --extra admin --extra dev --extra build
.venv/Scripts/python.exe -X utf8 scripts/build_release.py --version 1.0.1 --notes "Mô tả ngắn thay đổi"
```

Mặc định lệnh dùng FFmpeg/FFprobe trong PATH máy build. Có thể dùng `--ffmpeg-dir PATH_TO_BIN` cho bản Essentials đã kiểm tra checksum, và `--output-root dist/windows` để chọn thư mục xuất. Lệnh đối chiếu khóa công khai của hosting với dữ liệu quản trị cục bộ trước khi build, chỉ đưa khóa công khai vào gói. Cần giữ bản backup quản trị đồng bộ; nếu thay máy build, khôi phục cặp database/secrets vào vùng riêng tư trước.

3. Build tạo ZIP và JSON đã ký trong `dist/LiveStudio-VERSION`. Không sửa ZIP sau khi ký. Bản xuất đã tồn tại sẽ không bị ghi đè; chọn thư mục xuất mới khi build lại cùng một phiên bản chưa phát hành.
4. Kiểm tra gói, rồi đăng nhập trang admin HTTPS và tải cặp ZIP/JSON mới lên. Không cần deploy lại server nếu chỉ thay đổi ứng dụng Windows.
5. Khi khách mở tool và kích hoạt thành công, tool kiểm tra phiên bản mới; cũng có nút kiểm tra trong Cài đặt. Khách đồng ý tải, tool xác minh chữ ký và hash, xin xác nhận dừng/hoàn tất video rồi đóng và mở lại. Không ép cập nhật khi đang ghi.

Giữ một bản sao lưu riêng, ngoài máy hiện tại, của `.release-signing/update-signing.key`. Mất khóa này sẽ làm các bản đã gửi không tin các gói mới ký bằng khóa khác. Không đưa tệp này vào GitHub, hosting, ZIP khách hàng hay chat. Chữ ký gói cập nhật khác với chứng thư nhà phát hành Windows; EXE hiện chưa có Authenticode nên có thể xuất hiện SmartScreen.

## Kiểm tra thực tế

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/ruff.exe check .
.venv/Scripts/python.exe -X utf8 diagnostics/packaging_check.py --app-dir dist/windows/LiveStudio-1.0.0/LiveStudio
```

Chẩn đoán cuối dùng bản EXE và updater thật, dữ liệu riêng trong `build/`, PATH không có Python/FFmpeg cài sẵn, Qt offscreen, mã phiên bản QA 1.0.1 chưa phát hành. Nó kiểm tra tiến trình con, FFmpeg/FFprobe, DPAPI, nâng cấp thật, khởi động lại, giữ kênh/cài đặt và bản cũ. Bản QA không được công bố. Test tự động cũng kiểm tra từ chối ZIP độc hại, tải sai hash, hủy tải, khôi phục khi EXE mới không mở được và không xác nhận thành công khi khởi tạo database/giao diện lỗi.

Sau triển khai vẫn cần thử trên máy khách thứ hai: kích hoạt một key thử, ghi ngắn một phiên đang live, dừng xuất MP4, rồi thử cập nhật khi có bản phát hành tiếp theo. Kiểm tra proxy Vibe Host cho phép tải và tải lên từng phần, và dữ liệu vẫn còn qua Redeploy. Không tuyên bố đã kiểm tra Windows 10 hoặc mọi phần mềm antivirus nếu chưa có máy tương ứng.
