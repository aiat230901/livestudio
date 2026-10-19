# Thiết kế tool ghi livestream TikTok — bản 1

Ngày: 18/10/2026. Trạng thái: bản thiết kế để chủ tool duyệt ở giai đoạn 2; chưa triển khai các chức năng mới.

## 1. Mục tiêu và phạm vi đã thống nhất

Khách hàng dùng ứng dụng Windows tiếng Việt, nhận dưới dạng ZIP, giải nén và mở EXE. Ứng dụng ghi livestream trực tiếp từ TikTok về máy khách, hỗ trợ nhiều kênh cùng lúc. Mỗi kênh được chọn theo dõi liên tục hoặc theo lịch, và có thời lượng ghi tối đa riêng.

Chủ tool quản lý key một thiết bị trên trang admin online. Trang admin, chức năng xác thực key và database chạy trên hosting, độc lập với máy cá nhân của chủ tool. Vibe Host là nơi dự kiến triển khai, cần xác minh bằng bản triển khai thực tế ở giai đoạn 6.

Đã thử ghi ngắn đồng thời hai kênh thật và kiểm tra giải mã đầu ra sau khi sửa ba lỗi ở giai đoạn 1. Điều này xác nhận đường ghi ngắn; không phải kết quả kiểm tra chạy dài.

## 2. Các lựa chọn mặc định đề xuất

Các giá trị sau là đề xuất của bản thiết kế này, chưa phải cấu hình người dùng đã duyệt:

| Nội dung | Đề xuất |
|---|---|
| Chế độ khi thêm kênh | Theo dõi liên tục |
| Chu kỳ kiểm tra kênh chưa live | 2 phút, người dùng được đổi trong cài đặt |
| Thời lượng mỗi phiên | Không giới hạn, hoặc nhập giờ/phút riêng cho từng kênh |
| Múi giờ lịch | Giờ Việt Nam, hiển thị rõ UTC+7 |
| Đóng cửa sổ bằng nút X | Thu nhỏ xuống khay hệ thống; lần đầu giải thích rõ |
| Thoát hẳn | Lệnh Thoát trong menu, xác nhận nếu đang ghi |
| Sau khi mở lại ứng dụng | Khôi phục theo dõi cho những kênh đã bật trước đó |
| Tự mở cùng Windows | Tùy chọn, mặc định tắt |
| Key | Một key cho một thiết bị đang được kích hoạt |
| Thời hạn key | Tính từ lần kích hoạt đầu tiên |
| Kiểm tra key | Khi mở tool và định kỳ 15 phút |
| Máy chủ key mất kết nối | Cho phép tối đa 24 giờ từ lần xác thực thành công gần nhất, không vượt hạn key |

Chu kỳ kiểm tra không quyết định độ dài video. Nếu kiểm tra mỗi 2 phút, có thể phát hiện live chậm tới khoảng một chu kỳ cộng thời gian kết nối; không lấy lại được phần đã phát trước lúc bắt đầu ghi.

## 3. Giao diện dành cho khách

### 3.0. Phong cách giao diện đã thống nhất

Light mode, tối giản, dễ sử dụng và có tính thẩm mỹ. Tham chiếu trực quan là ảnh dashboard LarVoice Studio do chủ tool gửi trong hội thoại: nền xám rất nhạt, các khối trắng bo góc, viền mảnh, bóng nhẹ, chữ tối rõ và màu nhấn xanh dương. Giữ ngôn ngữ hình ảnh của mẫu, điều chỉnh nội dung cho quản lý livestream; không sao chép thương hiệu, nội dung audio hoặc tài nguyên của sản phẩm trong ảnh.

Bảng màu triển khai đề xuất, ước lượng theo ảnh chứ chưa phải lấy mẫu pixel: nền ứng dụng #F6F8FC, khối nội dung #FFFFFF, xanh chủ đạo #2563EB, xanh khi rê chuột #1D4ED8, nền xanh nhạt #EFF6FF, chữ chính #111827, chữ phụ #64748B và viền #E2E8F0. Khi triển khai kiểm tra lại độ tương phản trên các điều khiển thực tế.

Thanh điều hướng trái có Tổng quan, Kênh theo dõi, Lịch ghi, Lịch sử video và Cài đặt; trạng thái giấy phép ở phía dưới. Mục đang chọn có nền sáng, biểu tượng hoặc dấu nhấn xanh. Các chức năng chưa có trong từng giai đoạn không hiển thị nút hoạt động giả.

Tổng quan có phần giới thiệu ngắn nền xanh nhạt và bốn ô thống kê: Kênh theo dõi, Đang ghi, Chờ live/lịch và Video hôm nay. Bên dưới ưu tiên danh sách kênh cùng hoạt động gần đây. Kênh theo dõi vẫn là màn hình thao tác chính, không bắt người dùng đi qua dashboard để ghi.

Nút chính như Thêm kênh, Bật theo dõi và Lưu dùng nền xanh dương với chữ trắng. Nút phụ như Chọn thư mục dùng nền trắng và viền mảnh. Dừng dùng kiểu trung tính hoặc viền; thao tác xóa hoặc cảnh báo nghiêm trọng mới dùng đỏ để phân biệt mức độ. Biểu tượng dạng nét đơn giản, bo góc khối khoảng 12–16 px và bố cục thoáng theo tinh thần ảnh mẫu.

Ưu tiên danh sách kênh rõ ràng và những thao tác thường dùng; cài đặt nâng cao nằm trong phần riêng, không chiếm màn hình chính.

Nút có nhãn tiếng Việt dễ hiểu; màu trạng thái luôn đi kèm chữ, không chỉ dùng màu để phân biệt. Phông chữ và kích thước điều khiển phù hợp Windows, hỗ trợ phóng to hiển thị và thao tác bằng bàn phím. Không cần chế độ tối trong bản đầu.

### 3.1. Kích hoạt

Lần đầu mở: ô nhập key, nút Kích hoạt, mã thiết bị để hỗ trợ và thông báo lỗi dễ hiểu. Hiển thị số ngày còn lại sau khi kích hoạt. Không yêu cầu khách nhập thông tin quản trị hoặc cài Python.

Thông báo phân biệt key không hợp lệ, hết hạn, bị khóa, đã gắn máy khác và không kết nối được máy chủ. Chỉ chủ tool được reset thiết bị.

### 3.2. Màn hình Kênh theo dõi

Thanh trên: Thêm kênh, Bật theo dõi tất cả, Tắt theo dõi tất cả, Mở thư mục video. Tắt theo dõi sẽ ngừng kiểm tra và dừng ghi có lưu dữ liệu; xác nhận khi tác động tới kênh đang ghi.

Bảng chính gồm:

| Cột | Nội dung |
|---|---|
| Theo dõi | Bật/tắt từng kênh |
| Kênh | Username chuẩn hóa, ví dụ @sacngockhang_official |
| Chế độ | Liên tục / Theo lịch |
| Lịch | Luôn theo dõi hoặc khung giờ kế tiếp |
| Tối đa mỗi phiên | Không giới hạn hoặc giờ/phút |
| Trạng thái | Đang tắt, Chờ lịch, Chờ live, Đang ghi, Đang kết nối lại, Đang lưu, Đã đủ thời lượng, Lỗi |
| Đã ghi | Thời lượng và dung lượng file hiện tại |
| Thao tác | Ghi ngay, Dừng ghi, Sửa, Mở thư mục |

Dưới bảng có khu vực thông báo gần nhất, ghi rõ kênh và lý do kết thúc. Không hiển thị khóa bí mật, cookie hoặc đường dẫn CDN có chữ ký trong giao diện.

### 3.3. Thêm hoặc sửa kênh

Nhập username hoặc link hồ sơ/live đầy đủ. Ứng dụng chuẩn hóa về username, kiểm tra đầu vào và tránh thêm trùng kênh.

Các trường: chế độ theo dõi, thời lượng tối đa, thư mục lưu tùy chọn và các lịch của kênh nếu chọn Theo lịch. Mặc định dùng thư mục lưu chung, có thư mục con theo username. Có nút Chọn thư mục mở hộp thoại chọn thư mục của Windows; không bắt người dùng gõ đường dẫn. Kiểm tra quyền ghi và hiển thị rõ đường dẫn thực tế trước khi bắt đầu ghi.

Thời lượng gồm lựa chọn Không giới hạn hoặc số giờ/phút dương. Không dùng giá trị 0 để mang hai nghĩa khác nhau.

Sửa cấu hình kênh đang ghi áp dụng cho lần ghi tiếp theo. Nếu cần áp dụng ngay, người dùng dừng ghi trước; ứng dụng không âm thầm cắt file đang ghi.

### 3.4. Lịch sử video

Danh sách video có kênh, thời gian bắt đầu/kết thúc, độ dài, dung lượng, lý do dừng và đường dẫn. Cho mở video hoặc thư mục. Không tự xóa video cũ.

Chỉ báo Ghi thành công khi đã xác nhận có file đầu ra hợp lệ. Nếu chuyển MP4 thất bại thì giữ dữ liệu nguồn và báo lỗi, không coi là thành công.

### 3.5. Cài đặt

Thư mục lưu chung được chọn từ bất kỳ thư mục hợp lệ nào trên ổ đĩa máy khách mà người dùng có quyền ghi; có nút Chọn thư mục và Mở thư mục. Người dùng cũng có thể đặt thư mục riêng cho từng kênh. Các cài đặt khác gồm chu kỳ kiểm tra live, tùy chọn tự mở cùng Windows và thông báo khi ghi xong hoặc có lỗi. Có phần trạng thái giấy phép, ngày hết hạn và hướng dẫn liên hệ chủ tool.

Cấu hình cookie chỉ cần khi gặp tài khoản hoặc kết nối yêu cầu đăng nhập; là phần nâng cao. Cookie TikTok và video ở máy khách, không gửi lên hệ thống cấp key. Cookie cần được lưu bằng cơ chế bảo vệ của Windows, không ghi vào log.

## 4. Quy tắc ghi và giới hạn mỗi phiên

Một phiên được nhận diện bằng username và room ID TikTok. Một kênh chỉ có một tác vụ ghi tại một thời điểm; nhấn nút nhiều lần không tạo các bản ghi trùng.

Thời lượng tối đa là giới hạn tính từ lúc bắt đầu tác vụ ghi của phiên, bao gồm thời gian thử kết nối lại; không bị đặt lại khi đổi nguồn tải. Trong lúc chạy dùng đồng hồ đơn điệu; lưu mốc kết thúc theo UTC để khôi phục sau khi mở lại tool. Thời gian chuyển file sang MP4 có thể diễn ra sau khi đã dừng thu dữ liệu.

Ví dụ đặt tối đa 1 giờ:

- Live kết thúc sau 30 phút: lưu phần đã thu được và báo Livestream đã kết thúc.
- Live kéo dài hơn 1 giờ: dừng ở giới hạn, lưu file và báo Đã đủ thời lượng; chỉ tự ghi lại khi phát hiện room ID của phiên mới.
- Đến cuối lịch trước 1 giờ: dừng, lưu file và báo Hết khung giờ ghi.
- Người dùng bấm Dừng ghi: lưu file và dừng tự ghi phiên hiện tại; việc theo dõi các phiên mới vẫn tiếp tục nếu kênh đang bật.
- Đóng rồi mở tool sau khi đã đủ thời lượng: vẫn nhớ phiên đã hoàn tất, không ghi lại cùng room ID.

Kết quả video có thể ngắn hơn thời gian đặt do thời điểm nhận dữ liệu, phần dữ liệu chưa hoàn chỉnh bị loại bỏ hoặc mất kết nối. Không thêm hình đen hoặc khoảng trống để kéo đủ thời lượng.

Khi gián đoạn kết nối mà room ID không đổi, đó vẫn là cùng phiên; không tính lại hạn mức. Nếu phải tạo file phục hồi riêng thì tổng tác vụ vẫn chịu cùng mốc kết thúc. Không ghép tùy tiện dữ liệu của hai kết nối nếu làm hỏng video.

Nếu không xác định được trạng thái live do lỗi mạng, hiển thị Đang kết nối lại; không kết luận Livestream đã kết thúc chỉ từ lỗi mạng. Khi xác nhận phiên đã kết thúc mới hiển thị thông báo kết thúc live.

Ghi ngay được phép bỏ qua lịch bằng thao tác chủ động của người dùng, nhưng vẫn chịu giới hạn mỗi phiên. Phiên đã đạt giới hạn không thể tự bắt đầu lại bằng nút này. Phiên người dùng dừng sớm có thể được ghi tiếp bằng Ghi ngay trong thời gian còn lại của mốc giới hạn ban đầu.

Khi không giới hạn thời lượng, tác vụ dừng khi live kết thúc, hết lịch, người dùng dừng hoặc gặp lỗi không thể tiếp tục. Có mạng lại sẽ tiếp tục theo quy tắc trên, không có cơ chế lấy lại những đoạn đã bỏ lỡ.

## 5. Quy tắc đặt lịch

Mỗi kênh chọn Liên tục hoặc Theo lịch. Liên tục không yêu cầu biết trước giờ live. Theo lịch chỉ kiểm tra và tự ghi trong các khoảng được chọn.

Hỗ trợ lịch một lần với ngày giờ bắt đầu/kết thúc, hoặc lịch lặp theo các ngày trong tuần. Cho nhiều khung giờ trên cùng kênh, nhưng các khung trùng/tiếp giáp được xem là một khoảng liên tục để không dừng rồi ghi trùng.

Lịch 22:00–02:00 kết thúc vào ngày hôm sau; ngày trong tuần là ngày bắt đầu khung giờ. Cấm lịch có cùng giờ bắt đầu/kết thúc; muốn theo dõi cả ngày dùng Liên tục. Ngày giờ hiển thị luôn theo múi giờ đã chốt, không âm thầm đổi khi Windows đổi múi giờ.

Đến giờ mà chưa live thì chờ và kiểm tra theo chu kỳ. Đến giờ mà đang live thì ghi từ thời điểm kết nối được. Hết giờ thì đóng file an toàn.

Nếu cùng room ID vẫn live ở khung giờ sau, chỉ được ghi tiếp khi phiên chưa hết mốc thời lượng tối đa và người dùng chưa chủ động dừng phiên. Mốc giới hạn không được tính lại theo từng lịch. Với lựa chọn Không giới hạn, khung giờ sau có thể ghi lại phần tiếp theo của cùng phiên.

Lịch không tự bật máy hoặc đánh thức máy đang ngủ. Khi mở lại tool trong khung giờ còn hiệu lực, kiểm tra ngay; không chạy bù một lịch đã hết.

## 6. Vận hành trên máy khách

Máy khách phải bật, có mạng và tool còn chạy. Cửa sổ có thể thu nhỏ xuống khay hệ thống. Mất điện hoặc tắt cưỡng bức có thể để lại file nguồn cần phục hồi; khi mở lại, nhận diện và thử hoàn tất file đó thay vì xóa.

Đầu ra mặc định là MP4 có hình và tiếng. Ưu tiên chất lượng cao nhất trong các nguồn TikTok mà tool lấy và tải được tại thời điểm ghi; chuyển sang nguồn thấp hơn khi nguồn cao hơn không dùng được và thông báo rõ việc chuyển. Không coi nguồn chỉ có âm thanh là một bản ghi video thành công.

Giữ nguyên luồng hình/tiếng và chuyển cách đóng gói sang MP4 khi codec tương thích, tránh nén lại làm giảm chất lượng. Đây là chất lượng cao nhất truy cập được từ nguồn live, không phải cam kết luôn có Full HD/4K hoặc chất lượng tương đương video gốc của người phát. Không tự nâng độ phân giải. Giao diện hiển thị độ phân giải của bản ghi khi xác định được.

Không hứa số kênh đồng thời không giới hạn: thực tế phụ thuộc mạng, ổ đĩa và máy khách. V1 không đặt một số kênh tùy tiện trước khi có kết quả đo.

Không ghi đè file cũ: tên file có username, thời điểm và phần phân biệt khi trùng tên. Báo lỗi rõ nếu thiếu quyền ghi hoặc hết dung lượng, giữ phần dữ liệu đã thu được và không để lỗi một kênh làm dừng các kênh khác.

## 7. Key và admin online

Admin đăng nhập riêng; bảng key gồm ghi chú khách hàng, thời hạn gói, trạng thái, ngày kích hoạt/hết hạn, thiết bị và lần kiểm tra gần nhất.

Thao tác: tạo một hoặc nhiều key; gia hạn; khóa/mở khóa; reset thiết bị; tìm kiếm/lọc; sao lưu dữ liệu. Mọi thay đổi quản trị được ghi lịch sử. V1 cấp key thủ công, không cần thanh toán tự động.

Tạo key chưa làm chạy đồng hồ thời hạn. Kích hoạt đầu tiên thành công mới tính hạn; xử lý trên server để hai máy không đồng thời chiếm một key. Reset thiết bị bỏ liên kết máy cũ nhưng không tự gia hạn key. Gia hạn key còn hạn thì cộng từ ngày hết hạn; key đã hết hạn thì tính từ thời điểm gia hạn.

Quyền admin được kiểm tra trên server ở mọi thao tác. Tool khách không chứa mật khẩu admin, khóa ký giấy phép hoặc thông tin kết nối database. Database lưu dữ liệu key và thiết bị ở mức tối thiểu cần dùng; không thu video, danh sách kênh hay cookie để cấp phép.

Máy chủ trả giấy phép có xác thực, gắn thiết bị và ngày hết hạn. Mất kết nối máy chủ chỉ dùng giấy phép đã xác thực trong khoảng dung sai đề xuất; key mới chưa từng xác thực không được kích hoạt offline. Hết hạn thực sự không được kéo dài bằng khoảng dung sai.

Khi nhận kết quả key hết hạn hoặc bị khóa: dừng tác vụ có lưu dữ liệu, không cho bắt đầu ghi mới và hiển thị lý do. Không xóa video của người dùng. Khóa từ xa có hiệu lực khi máy khách nhận kết quả kiểm tra, không cam kết tức thời nếu mất kết nối.

## 8. Cấu trúc hệ thống và tiến độ triển khai

Ứng dụng Windows gồm giao diện, bộ theo dõi/lịch, các tiến trình ghi độc lập và nơi lưu trạng thái cục bộ. Giao diện không bị khóa khi ghi hoặc kiểm tra mạng. Trạng thái phiên đã đạt giới hạn được lưu cục bộ để không bị mất khi khởi động lại.

Hệ thống online gồm một ứng dụng web chứa admin và API giấy phép, cùng một database độc lập. Dùng HTTPS. Video đi trực tiếp từ TikTok về máy khách, không trung chuyển qua máy chủ key. Có sao lưu và quy trình phục hồi dữ liệu key.

Đóng gói ZIP Windows chứa EXE, môi trường chạy và FFmpeg cần thiết. Các bản cập nhật phải giữ cấu hình, dữ liệu phiên, trạng thái kích hoạt và video. Giữ thông báo giấy phép của mã nguồn/thành phần được phân phối.

Triển khai theo các giai đoạn đã thống nhất:

1. Giai đoạn 3: giao diện, nhiều kênh, theo dõi liên tục, thời lượng tối đa mỗi phiên, trạng thái và lịch sử.
2. Giai đoạn 4: lịch một lần/lặp lại, qua đêm, hết lịch và xử lý lịch trùng.
3. Giai đoạn 5: admin và hệ thống key chạy thử.
4. Giai đoạn 6: triển khai hệ thống online lên hosting.
5. Giai đoạn 7: tích hợp kích hoạt vào tool và đóng gói Windows.
6. Giai đoạn 8: kiểm thử bản phát hành, tài liệu và bàn giao.

Trước khi có hệ thống key, bản giao diện chỉ là bản thử nội bộ; không coi là bản sẵn sàng gửi khách.

## 9. Điều kiện nghiệm thu

- Thêm hai kênh, bật theo dõi, cả hai ghi được và tạo file hợp lệ độc lập.
- Kênh chưa live không bị coi là lỗi; khi phát hiện live thì ghi và cập nhật trạng thái.
- Đặt thời lượng ngắn: dừng đúng quy tắc, file giải mã được, không tự ghi lại cùng phiên kể cả sau khi mở lại tool.
- Đặt thời lượng dài nhưng nguồn kết thúc sớm: lưu file ngắn, thông báo live kết thúc; lỗi mạng có trạng thái khác.
- Lịch một lần, lặp lại, qua đêm và trùng nhau chạy đúng; không tạo hai bản ghi cùng kênh.
- Dừng, thoát và lỗi một kênh không làm mất video đã ghi của các kênh khác.
- Key đầu tiên kích hoạt trên một máy; máy thứ hai bị từ chối; reset và gia hạn hoạt động đúng.
- Hết hạn/khóa/mất máy chủ xử lý theo quy tắc, không xóa video và không lộ thông tin quản trị.
- Khách trên máy Windows thử nghiệm giải nén và dùng được, không phải cài Python.

Kiểm thử giai đoạn phát triển hiện tại ưu tiên mẫu ngắn theo yêu cầu của chủ tool. Không suy ra độ ổn định nhiều giờ từ các mẫu ngắn; nếu chưa thử chạy dài trước phát hành thì ghi rõ giới hạn trong bàn giao.
