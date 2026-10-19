# Bản thử Live Studio — giai đoạn 4

Trong thư mục dự án, bấm đúp **Mo_Tool.bat** để mở ứng dụng.
Bản trên máy hiện tại đã được cài môi trường và giao diện. Đây là bản thử từ
mã nguồn; chưa phải ZIP/EXE tự chứa để gửi khách.

## Sử dụng

1. Bấm **Thêm kênh**, nhập `@username` hoặc link hồ sơ/live đầy đủ của TikTok.
2. Chọn **Không giới hạn** hoặc số giờ/phút tối đa cho mỗi phiên live.
3. Chọn thư mục riêng nếu muốn. Nếu để trống, video vào thư mục chung,
   bên trong có thư mục theo username. Đổi thư mục chung tại **Cài đặt**.
4. Chọn **Liên tục** hoặc **Theo lịch**, rồi bật **Theo dõi kênh này**.
   Mặc định tool kiểm tra mỗi 2 phút khi kênh được phép chạy;
   chưa live thì chờ, phát hiện live thì ghi. Các kênh chạy độc lập.
5. Chọn một dòng kênh để **Ghi ngay**, **Dừng ghi**, sửa hoặc mở thư mục.
   Tắt theo dõi cũng dừng tác vụ hiện tại và giữ phần đã ghi.
6. Mở **Lịch sử video** để xem file, độ dài, độ phân giải và lý do kết thúc.
   Video MP4 hợp lệ có hình và tiếng; bản lỗi xuất giữ tệp nguồn để phục hồi.

Thời lượng là hạn mức tính từ khi tác vụ của phiên bắt đầu, gồm cả thời gian
kết nối và thử lại. Ví dụ đặt 1 giờ nhưng live kết thúc sau 30 phút thì lưu
phần nhận được và báo **Live đã kết thúc**. Video thực tế có thể ngắn hơn
thời gian tác vụ vì cần kết nối, chờ khung hình đầu và bỏ gói cuối chưa đầy đủ.

Đạt giới hạn sẽ chờ room ID mới, kể cả sau khi mở lại tool. **Dừng ghi** bỏ
qua phần còn lại của phiên đó; **Ghi ngay** có thể tiếp tục nếu hạn mức cũ còn.
Không tạo lại hạn mức khi bấm ghi, sửa kênh, xóa/thêm lại hoặc mở lại ứng dụng.

Mất mạng được báo riêng với live kết thúc. Khi theo dõi đang bật, tool thử
lại sau lỗi mạng, lưu mỗi đoạn thành một file riêng cùng hạn mức phiên cũ;
không nối mù các đoạn gây hỏng video. Khi mở lại, tool thử hoàn tất các tệp
nguồn `TK_<username>_*_flv.mp4` còn trong thư mục hiện tại của kênh.
Không xóa tệp nguồn nếu không chuyển được.
Với Theo lịch, bước phục hồi này thực hiện khi kênh được kiểm tra lần đầu
trong khung giờ được phép hoặc khi người dùng bấm Ghi ngay.

## Đặt lịch riêng cho kênh

Khi thêm/sửa kênh, chọn **Theo lịch**, bấm **Thêm khung giờ** rồi lưu kênh.
Hoặc vào mục **Lịch ghi**, chọn kênh ở ô **Thêm lịch cho** và bấm **Thêm lịch**.
Thêm lịch từ màn hình này sẽ chuyển kênh sang Theo lịch; cờ bật/tắt theo dõi
của kênh vẫn giữ nguyên. Bật theo dõi để lịch tự chạy.

- **Một lần:** chọn ngày giờ bắt đầu và kết thúc; kết thúc phải sau bắt đầu.
- **Lặp hằng tuần:** chọn T2–CN và giờ bắt đầu/kết thúc. Ví dụ chọn T2,
  22:00–02:00 thì ghi từ tối thứ Hai đến rạng sáng thứ Ba. Không chọn hai
  giờ giống nhau; muốn theo dõi cả ngày có thể dùng Liên tục.
- Mỗi kênh có nhiều khung giờ. Các khung trùng hoặc tiếp giáp được ghép thành
  một khoảng ghi liên tục, không tạo tác vụ hoặc file trùng vì lịch chồng nhau.
- Toàn bộ lịch dùng **giờ Việt Nam UTC+7**, không tự đổi theo múi giờ Windows.

Đến giờ sẽ kiểm tra ngay; nếu chưa live thì kiểm tra lại theo chu kỳ trong
Cài đặt. Hết khung giờ sẽ dừng thu, hoàn tất MP4 và báo **Hết khung giờ ghi**.
Việc đóng file có thể hoàn tất sau mốc lịch do chờ mạng/ổ đĩa/FFmpeg.
Ngoài lịch, kênh ở trạng thái **Chờ lịch** và không kiểm tra live tự động.

Giới hạn mỗi phiên vẫn tính từ lần bắt đầu tác vụ đầu tiên, bao gồm khoảng
nghỉ giữa các khung giờ. Ví dụ hạn mức 1 giờ bắt đầu lúc 22:00 thì mốc cuối
vẫn là 23:00, dù giữa hai lịch có nghỉ. Ở khung sau, cùng phiên chỉ được ghi
tiếp nếu còn hạn mức và người dùng chưa bấm Dừng ghi. Với Không giới hạn,
cùng phiên có thể ghi tiếp ở khung sau. Phiên live mới có hạn mức mới.

**Ghi ngay** bỏ qua lịch nhưng vẫn giữ giới hạn phiên. Để chạy liên tục trở
lại, vào **Sửa kênh** và chọn **Liên tục**. Xóa lịch cuối cùng của kênh đang
Theo lịch sẽ để kênh chờ thêm lịch, không tự chuyển sang chạy cả ngày.
Hãy dừng tác vụ hiện tại trước khi sửa lịch của kênh đang kiểm tra hoặc ghi.

Tool không bật máy hoặc đánh thức máy đang ngủ. Mở lại trong khung còn hiệu
lực sẽ kiểm tra ngay; khung đã hết không chạy bù. Cấu hình cũ từ giai đoạn 3
được giữ và mặc định tiếp tục ở chế độ Liên tục.

## Đóng và mở lại

- Bấm **X** để thu xuống khay hệ thống; tool vẫn chạy. Bấm biểu tượng khay
  để mở lại. Nếu hệ thống không có khay, X chuyển sang thoát có kiểm soát.
- Dùng **Thoát ứng dụng** để dừng và xuất MP4 trước khi đóng.
  Chờ hoàn tất khi mạng hoặc ổ đĩa đang chậm; không tắt cưỡng bức.
- Chỉ một ứng dụng dùng cùng dữ liệu được chạy. Mở lần hai sẽ báo tool đang chạy.
- Các kênh đã bật được khôi phục khi mở lại. Máy cần bật, có mạng và không ngủ.
- **Mở tool cùng Windows** mặc định tắt; chỉ thay đổi đăng ký khởi động
  cho tài khoản Windows hiện tại khi người dùng bật/tắt tùy chọn này.

Cấu hình/phiên/lịch sử mặc định nằm trong
`%LOCALAPPDATA%\TikTokLiveStudio\state.db`. Video nằm ở thư mục đã chọn,
không nằm trong database. Không lưu cookie vào database.

## Cài môi trường thử trên máy phát triển khác

Cần Python >=3.11, uv, FFmpeg và FFprobe trên PATH. Tại thư mục dự án:

```powershell
uv sync --frozen --extra desktop --extra dev --cache-dir .cache/uv
.venv/Scripts/python.exe -m desktop.app
```

Launcher không tự tải hoặc cài thêm phần mềm.

## Phạm vi và kiểm tra

Đã làm: light mode, nút xanh, nhiều kênh, theo dõi liên tục, thời lượng,
chọn thư mục, trạng thái, lịch sử, khay hệ thống, lưu cấu hình và đặt lịch
một lần/lặp lại/qua đêm, admin quản lý key và kích hoạt giấy phép trên Windows.
Hosting/EXE chưa hoàn thành. Trước khi mở tool, làm theo
[hướng dẫn kích hoạt](HUONG_DAN_KICH_HOAT.md) để mở máy chủ và tạo key thử.

Ưu tiên nguồn video tải được có chất lượng cao nhất; không nâng độ phân giải,
không cam kết Full HD/4K. Bản thử hiện dùng luồng tải trực tiếp (FLV);
nguồn chỉ có danh sách HLS cần bổ sung bộ tải HLS trước phát hành.
Nguồn chỉ âm thanh không được coi là video thành công.

Kiểm tra tự động:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe diagnostics/phase3_check.py
.venv/Scripts/python.exe diagnostics/phase4_check.py
```

Kiểm tra thật ngắn với hai kênh đã cung cấp, chỉ khi có mạng/live:

```powershell
.venv/Scripts/python.exe diagnostics/phase3_check.py --live
```

Báo cáo và ảnh ở `diagnostics/phase3-*`, `diagnostics/phase4-*`. Kiểm tra lịch
dùng đồng hồ điều khiển và nguồn mẫu; có kiểm tra tiến trình/FFmpeg thật,
không coi đó là chạy TikTok thật suốt đêm hoặc cả tuần.
Bản thử chưa được kiểm tra chạy nhiều
giờ, tải lớn, mất điện hoặc trên máy Windows sạch chưa cài môi trường.
Kiểm tra cửa sổ bằng Qt tự động không thay thế việc người dùng dùng thử thực tế.
