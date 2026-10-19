# Giai đoạn 3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bản ứng dụng Windows chạy thử với giao diện sáng theo ảnh mẫu, nhiều kênh, theo dõi liên tục, giới hạn từng phiên, thư mục lưu và lịch sử.

**Architecture:** Giữ bộ ghi và CLI hiện tại. Thêm ứng dụng desktop với một bộ điều phối chạy trên luồng giao diện, các tiến trình riêng cho công việc mạng/ghi, và SQLite cục bộ chỉ do bộ điều phối cập nhật. Lưu quyết định bắt đầu/dừng phiên trước khi tạo tác vụ để tránh ghi lại cùng phiên sau khởi động lại.

**Tech Stack:** Python hiện có, PySide6/Qt Widgets cho desktop, SQLite và multiprocessing từ thư viện chuẩn, FFmpeg/FFprobe hiện có. PySide6 là dependency tùy chọn `desktop`; CLI vẫn dùng được khi không cài desktop. Tham khảo chính thức: https://doc.qt.io/qtforpython-6/gettingstarted.html và https://doc.qt.io/qtforpython-6.10/PySide6/QtWidgets/QSystemTrayIcon.html.

**Spec:** `docs/THIET_KE_TOOL_V1.md`, phần giai đoạn 3 và các quy tắc chung. Không triển khai lịch, admin, key hoặc ZIP phát hành ở giai đoạn này.

## Global Constraints

- Light mode theo mẫu: nền #F6F8FC, khối trắng, nút #2563EB, chữ #111827, viền #E2E8F0; tiếng Việt có dấu.
- Một tác vụ ghi cho một kênh; hai kênh phải chạy đồng thời mà không chặn giao diện.
- Mặc định liên tục, kiểm tra mỗi 2 phút; thời lượng mặc định không giới hạn, cấu hình giờ/phút riêng từng kênh.
- Một room ID chỉ có một hạn mức cho phiên. Không đặt lại hạn mức khi kết nối lại, mở lại ứng dụng hoặc đổi nguồn.
- Thời lượng là thời gian tối đa của tác vụ, gồm thời gian thử kết nối lại; lưu mốc UTC để khôi phục và dùng đồng hồ đơn điệu lúc đang chạy.
- Đầu ra MP4 ưu tiên chất lượng video/âm thanh cao nhất lấy được; nguồn chỉ âm thanh không được coi là ghi video thành công.
- Chọn thư mục Windows, lưu cài đặt và lịch sử; không ghi đè hay xóa video cũ.
- Lỗi mạng khác với xác nhận live kết thúc. Không hiển thị thành công khi xuất MP4 thất bại.
- X thu xuống khay; Thoát lưu và dừng có kiểm soát. Không giết tiến trình đang ghi như cách dừng bình thường.
- Các mục lịch/key chưa làm không có nút giả hoặc thông báo kích hoạt giả.
- Bản đang làm là bản thử nội bộ; đóng gói EXE cho khách thuộc giai đoạn 7.

## Review Focus

1. Hai lần bật hoặc mở hai cửa sổ không được ghi trùng cùng kênh — khóa một phiên ứng dụng và kiểm thử yêu cầu bắt đầu lặp ở Task 3/4.
2. Tắt/mở ứng dụng đúng lúc bắt đầu ghi không được mất hạn mức — kiểm thử lưu phiên trước khi khởi chạy worker và khôi phục ở Task 1/3.
3. Dừng khi mạng không trả dữ liệu không được treo giao diện hoặc mất file — timeout và dừng hợp tác ở Task 2/3.
4. Thư mục có dấu, đường dẫn không ghi được, file trùng tên — kiểm thử tên file và chọn thư mục ở Task 1/2/4.
5. Key chưa làm, lịch chưa làm và màn hình trống phải được thể hiện đúng phạm vi — kiểm thử luồng giao diện có dữ liệu và rỗng ở Task 4/5.

## Trước khi triển khai

- [ ] Chủ tool duyệt kế hoạch này và chọn cách thực hiện. Đề xuất: tự triển khai trong phiên hiện tại; các task dùng chung nhiều trạng thái nên giảm chi phí bàn giao.
- [ ] Ghi mốc baseline: `.venv/Scripts/python.exe -m pytest -q` hiện đạt 44 tests.
- [ ] Thư mục hiện không có `.git`. Không tự tạo repository hoặc giả định có worktree. Trước khi sửa sản phẩm, sao lưu chính xác các tệp hiện có sẽ sửa vào `diagnostics/phase3-backup/`, không kèm cookie, log, video hay môi trường Python; lưu bảng tệp sao lưu. Giữ ledger tại `diagnostics/phase3-progress.md`. Không có commit khi chưa có Git.

## Task 1: Mô hình kênh, phiên và dữ liệu lưu cục bộ

**Files:** Tạo `src/desktop/__init__.py`, `src/desktop/store.py`, `tests/test_desktop_store.py`.

**Interfaces:** `normalize_username(value: str) -> str`; `DesktopStore(path: Path)`; `save_channel(user: str, duration_seconds: int | None, output: str | None, enabled: bool) -> dict`; `list_channels() -> list[dict]`; `delete_channel(user: str)`; `get_setting(name: str, default=None)`; `set_setting(name: str, value)`; `get_session(user: str, room_id: str) -> dict | None`; `save_session(user: str, room_id: str, started_utc: float, deadline_utc: float | None, state: str)`; `add_recording(record: dict)`; `list_recordings() -> list[dict]`.

Kênh có username duy nhất, cấu hình và cờ bật. Phiên có khóa `(username, room_id)`, mốc bắt đầu/hết hạn và trạng thái active/completed/stopped. Lịch sử chứa đường dẫn, thời gian, độ dài media, dung lượng, lý do và trạng thái xuất. Dữ liệu SQLite đặt trong thư mục dữ liệu ứng dụng của người dùng; đường dẫn được truyền vào để tests không dùng dữ liệu thật. Dùng transaction và truy vấn có tham số.

- [ ] Viết tests: `@name`, username và link hồ sơ/live đầy đủ chuẩn hóa thành một kênh; từ chối link ngoài TikTok/đầu vào rỗng/username chứa ký tự đường dẫn; sửa kênh không nhân đôi. Thời lượng None hoặc số nguyên dương; từ chối âm/0.
- [ ] Viết tests: round-trip cấu hình; lưu deadline=1000 rồi mở lại vẫn 1000; trạng thái completed vẫn còn sau khởi động lại; lỗi giao dịch không để lại nửa bản ghi; đường dẫn có dấu lưu nguyên vẹn.
- [ ] Chạy `.venv/Scripts/python.exe -m pytest tests/test_desktop_store.py -q`, xác nhận thất bại vì chức năng chưa tồn tại.
- [ ] Triển khai store và validation; không lưu cookie vào SQLite.
- [ ] Chạy tests task và toàn bộ suite; chỉ ghi task complete vào ledger khi đạt.

## Task 2: Bộ ghi có thể dừng và trả kết quả rõ ràng

**Files:** Sửa `src/core/tiktok_recorder.py`, `src/core/tiktok_api.py`, `src/utils/video_management.py`; tạo `src/utils/recording_result.py`, `tests/test_recording_control.py`; cập nhật `tests/test_recording_integration.py` khi cần giữ fixture tương thích.

**Interfaces:** `RecordingResult(path: str | None, reason: str, bytes_written: int, error: str | None = None)`; `TikTokRecorder(config, stop_event=None, on_event=None)` giữ tương thích CLI. `start_recording(user, room_id) -> RecordingResult`; callback `on_event(kind: str, payload: dict)` là tùy chọn, gọi trong worker. `VideoManagement.convert_flv_to_mp4(...) -> str | None` trả đường dẫn chỉ khi thành công. `TikTokAPI.download_live_stream(live_url, timeout=None)` hỗ trợ timeout đọc phù hợp phần thời lượng còn lại.

Lý do trả về: `duration`, `live_ended`, `user_stop`, `network_error`, `conversion_error`. Sự kiện `progress` có bytes/thời gian, `finalizing` trước chuyển MP4. Tiến độ không cập nhật quá dày; không đưa cookie/URL có chữ ký vào sự kiện UI.

- [ ] Viết tests dừng hợp tác giữa các chunk: file hoàn tất hợp lệ, stream đóng, kết quả user_stop. Giữ ba hồi quy giai đoạn 1.
- [ ] Viết tests deadline không reset qua reconnect; retry dừng đúng hạn khi không có dữ liệu; lỗi kiểm tra mạng không bị phân loại live_ended; nguồn kết thúc sớm lưu video ngắn; lỗi chuyển đổi giữ nguồn và trả conversion_error.
- [ ] Viết tests file cùng kênh/cùng giây không ghi đè, thư mục có dấu; sự kiện tiến độ không chứa thông tin nhạy cảm; không nhận nguồn audio-only thành video thành công.
- [ ] Chạy tests mới, xác nhận các hành vi mới chưa đạt trước khi sửa mã.
- [ ] Thêm control và kết quả vào bộ ghi hiện có. Với lỗi làm gián đoạn FLV, hoàn tất phần hợp lệ trước khi tạo đoạn phục hồi mới; các đoạn dùng chung deadline phiên, không nối mù hai header FLV vào một file.
- [ ] Chạy tests task, kiểm tra giải mã các file mẫu và toàn bộ suite.

## Task 3: Bộ điều phối nhiều kênh và nhớ hạn mức phiên

**Files:** Tạo `src/desktop/manager.py`, `src/desktop/worker.py`, `tests/test_desktop_manager.py`.

**Interfaces:** `run_job(job: dict, events, stop_event)` chạy trong một tiến trình Windows spawn; job có `job_id`, `username`, kind=`probe`/`record`, output, duration còn lại và room ID nếu ghi. Sự kiện có `job_id`, `username`, `kind`, `payload`. `RecordingManager(store, process_factory=None, clock=None)` cung cấp `tick()`, `enable(user, enabled)`, `record_now(user)`, `stop_recording(user)`, `snapshot()`, `shutdown()`; `tick` nhận sự kiện, điều phối và trả nhanh, không gọi mạng trên luồng UI.

Mỗi kênh có tối đa một job. Probe phát hiện room ID; manager lưu session/deadline trong transaction trước khi tạo job ghi. Phiên completed không ghi lại; phiên stopped chỉ tiếp tục bằng Ghi ngay nếu chưa quá deadline. Room mới có hạn mức mới. Các bản ghi phục hồi vẫn dùng deadline phiên cũ. Khi đóng mở lại, kênh đã bật được khôi phục, phiên đã hết hạn không tự khởi động lại.

- [ ] Viết tests với process factory giả và đồng hồ điều khiển: hai kênh có hai job độc lập; bật lặp không tạo trùng; bật/tắt lúc đang probe; một lỗi không dừng kênh khác.
- [ ] Viết tests: cùng room đã đủ thời lượng bị bỏ qua sau mở lại; room mới được ghi; deadline lưu trước launch; job phát sự kiện cũ không ghi đè trạng thái job mới; dừng thủ công không bị tự bật lại.
- [ ] Viết tests: shutdown báo dừng và tiếp tục xử lý sự kiện hoàn tất; worker lỗi trước khi gửi kết quả không để kênh treo vĩnh viễn; lỗi mạng không đánh dấu phiên hoàn tất.
- [ ] Chạy tests mới để xác nhận chưa đạt, rồi triển khai manager/worker. Chỉ manager ghi SQLite; worker truyền kết quả qua queue.
- [ ] Chạy tests task và toàn bộ suite; kiểm tra spawn thật với nguồn FLV kiểm soát được.

## Task 4: Giao diện desktop theo mẫu đã duyệt

**Files:** Tạo `src/desktop/app.py`, `src/desktop/window.py`, `src/desktop/dialogs.py`, `src/desktop/theme.py`, `tests/test_desktop_ui.py`; sửa `pyproject.toml`, cập nhật `uv.lock` sau khi được duyệt.

**Interfaces:** `desktop.app.main() -> int`; `MainWindow(store, manager)`; `ChannelDialog(parent, initial=None)` trả cấu hình hợp lệ hoặc hủy; `SettingsDialog(parent, settings)` trả cài đặt hoặc hủy. `theme.apply_theme(app)` tạo light theme thống nhất. Thêm entry point `tiktok-live-recorder-gui = "desktop.app:main"` và optional dependency desktop `PySide6>=6.8,<7`.

Sidebar có Tổng quan, Kênh theo dõi, Lịch sử video, Cài đặt. Mục Lịch ghi chỉ thêm ở giai đoạn 4. Footer ghi rõ Bản thử nội bộ thay vì giả trạng thái giấy phép.

Tổng quan có bốn thẻ thống kê và hoạt động gần đây. Bảng kênh có trạng thái, bật/tắt, thời lượng tối đa, tiến độ và các nút ghi/dừng/sửa/mở thư mục. Dialog thêm/sửa có username/link, Không giới hạn hoặc giờ/phút và thư mục riêng. Các nút chính xanh dương; giao diện trắng/xám nhạt theo spec.

Lịch sử mở được video/thư mục và hiển thị lý do dừng. Cài đặt có thư mục chung, chu kỳ kiểm tra, thông báo và chạy cùng Windows (chỉ tạo mục khởi động khi người dùng bật). Nút X thu khay nếu khay khả dụng; nếu không có khay thì không ẩn ứng dụng vĩnh viễn. Thoát xác nhận khi đang ghi và đợi hoàn tất an toàn, vẫn cho giao diện phản hồi. Khóa ứng dụng duy nhất để không mở hai bộ điều phối dùng cùng database.

- [ ] Sau phê duyệt, cài dependency desktop vào .venv bằng uv và giữ lockfile nhất quán; không sửa Python toàn máy.
- [ ] Viết tests Qt offscreen với store tạm và manager giả: thêm/hủy/sửa/xóa, lỗi đầu vào không làm đóng dialog, chống thao tác trùng, đổi đường dẫn/chu kỳ và round-trip cấu hình.
- [ ] Viết tests: một yêu cầu ghi không chặn xử lý sự kiện Qt; trạng thái rỗng dễ hiểu; thống kê phản ánh dữ liệu thật; chuyển màn hình không mất chọn kênh; không có nút lịch/key giả.
- [ ] Chạy tests mới, rồi triển khai các màn hình, khay và theme. Chọn thư mục qua QFileDialog; mở đường dẫn bằng API hệ điều hành, không ghép shell command từ input.
- [ ] Chụp ảnh giao diện từ chính Qt ở kích thước 1440x900 và 1100x720; xem ảnh để sửa cắt chữ, tràn bảng và độ tương phản. Kiểm tra bằng bàn phím, độ phóng đại Windows và thao tác đóng/mở khay trong môi trường có GUI nếu khả dụng.
- [ ] Chạy tests task và toàn bộ suite. Nếu không kiểm tra được GUI Windows thật thì ghi rõ giới hạn, không gọi kiểm tra offscreen là kiểm tra tương tác thật.

## Task 5: Khởi chạy, nghiệm thu và bàn giao bản thử

**Files:** Tạo `Mo_Tool.bat`, `docs/HUONG_DAN_BAN_THU.md`, `diagnostics/phase3-report.json`; bổ sung bài kiểm tra đầu-cuối tại `tests/test_desktop_manager.py` và `tests/test_desktop_ui.py`.

Launcher dùng Python của .venv và entrypoint desktop trong thư mục dự án, xử lý đường dẫn có dấu/khoảng trắng. Nếu thiếu môi trường/dependency thì đưa thông báo hướng dẫn, không tự tải/cài khi khách bấm mở. Đóng gói tự chứa chưa thuộc giai đoạn này.

- [ ] Viết tests đầu-cuối với nguồn kiểm soát: thêm hai kênh, bật theo dõi, nhận hai file MP4 hợp lệ; giới hạn ngắn, khởi động lại, cùng phiên không ghi lại; phiên mới ghi được.
- [ ] Chạy tests trước khi hoàn thiện kết nối UI-manager; sửa kết nối để đạt, không thay engine bằng dữ liệu demo trong bản dùng thật.
- [ ] Nếu hai kênh còn live, thử ngắn `sacngockhang_official` và `ungthaimenuochoa` qua đường điều phối mới với dữ liệu thử tách biệt. Xác minh file bằng FFprobe và giải mã toàn bộ bằng FFmpeg. Không tự bắt đầu theo dõi dài trên dữ liệu người dùng.
- [ ] Kiểm tra `.venv/Scripts/python.exe -m pytest -q`, Ruff trên các tệp thay đổi, khởi động cửa sổ, lưu/mở lại cấu hình và launcher. Báo chính xác các kiểm tra chưa làm được.
- [ ] Review toàn bộ thay đổi theo spec, sửa lỗi quan trọng có kiểm thử hồi quy. Với inline execution, dùng reviewer ngữ cảnh mới theo executing-plans sau khi hoàn thành; không giao việc triển khai từng task nếu chưa được chọn.
- [ ] Ghi báo cáo kết quả, đường dẫn mở tool, ảnh giao diện và phạm vi chưa làm. Giữ nguyên dữ liệu/video/cookie của người dùng. Không triển khai giai đoạn 4–8 khi chưa được yêu cầu.

## Tự rà soát kế hoạch

- Phạm vi giai đoạn 3 có task tương ứng: dữ liệu (1), ghi có điều khiển (2), theo dõi/hạn mức (3), giao diện (4), chạy thử/bàn giao (5).
- Các giao diện dùng giữa task đã có tên và payload; worker không truy cập trực tiếp đối tượng Qt hoặc SQLite.
- Năm điều kiện Review Focus có bài kiểm tra trong các task được chỉ định.
- Không coi 44 tests baseline là bằng chứng cho các tính năng chưa viết; tests mới phải được thấy thất bại rồi đạt.
- Chưa cài PySide6, chưa tạo giao diện hoặc thay đổi mã sản phẩm trong bước viết kế hoạch này.

## Cách thực hiện để chủ tool chọn

**Đề xuất: inline/native** — tôi tự làm lần lượt năm task trong phiên này, cập nhật tiến độ và kiểm tra toàn bộ ở cuối; không dừng xin duyệt giữa từng task. Có review độc lập sau triển khai theo skill thực thi.

**Phương án khác: subagent theo từng task** — mỗi task có người triển khai và review riêng; nhiều lượt bàn giao và chi phí ngữ cảnh hơn.

Chỉ bắt đầu triển khai sau khi chủ tool duyệt kế hoạch bằng văn bản và chọn cách thực hiện. Việc đồng ý bản thiết kế trước đó không thay thế bước duyệt kế hoạch này.
