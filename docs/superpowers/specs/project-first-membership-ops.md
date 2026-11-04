# Vận hành: thêm thành viên theo project (project-first membership)

Tài liệu ngắn cho người vận hành. Thiết kế đầy đủ: `2026-11-04-project-first-membership-design.md`.

## Hành vi

- Workspace chỉ do super admin (god-mode) tạo, qua endpoint license của god-mode. Đặt `DISABLE_WORKSPACE_CREATION=1` (đã có trong `.env.prod.example`): `POST workspaces/` trả 403, god-mode không bị ảnh hưởng. Biến này cũng đọc được từ instance configuration.
- Project chỉ do workspace Admin trở lên tạo. Workspace Member tạo project nhận 403 (app API và API v1).
- Vào project: project Admin tìm user ĐÃ tồn tại (`GET workspaces/<slug>/projects/<id>/members/search/`, tối thiểu 3 ký tự, tối đa 10 kết quả, 30 lần/phút/user, email che một phần) rồi thêm. User chưa từng đăng nhập (Entra) thì chưa thêm được: không tìm thấy, và thêm trực tiếp trả 400 `USER_NOT_ELIGIBLE`.
- Khi thêm, hệ thống tự cấp workspace role: project Admin/Member -> workspace Member (15); project Guest -> workspace Guest (5). Role project không nhận diện được cũng bị ép về Guest.
- Hệ thống KHÔNG BAO GIỜ nâng role workspace đang active. Muốn nâng (ví dụ Guest lên Member để làm project Member/Admin) thì workspace Admin phải tự nâng role workspace.
- Gỡ user khỏi project cuối cùng: workspace member của user bị tắt (`is_active=False`), trừ workspace Admin và owner của workspace. Gỡ qua view/`.save()` thì xử lý ngay; còn lại do task định kỳ `ee-sweep-orphan-workspace-members` (celery beat, mỗi giờ phút 0) đối soát toàn bộ, kể cả khi project bị xóa mềm.
- Lưới an toàn: chỉ khi một dòng `ProjectMember` active được TẠO MỚI qua đường `.save()` khác thì receiver mới cấp workspace member. Không có override `partial_update` của ee: đổi role project dùng nguyên hành vi core.

## Công tắc god-mode "External invitations"

- Trang admin app: `/external-invites` (API: `GET/PATCH /api/instances/external-invites/`, khóa `ALLOW_EXTERNAL_INVITES`). Mặc định TẮT.
- TẮT: mọi đường mời (mời/join workspace, bulk accept, mời/join project, mời của API v1) trả 410 `INVITES_DISABLED`, không tạo dòng nào.
- BẬT: các endpoint đó chuyển tiếp xuống core (hành vi cũ, gồm cả lỗi sẵn có của core). Thêm trực tiếp vào project vẫn chỉ chấp nhận user đã tồn tại.

## Đăng ký / Entra

`ENABLE_SIGNUP=0` đòi lời mời mới đăng ký được (`authentication/adapter/base.py`). Migration `ee 0004` xóa hết lời mời, nên `ENABLE_SIGNUP=0` thì không ai mới vào được. Với Entra, giữ `ENABLE_SIGNUP=1` cùng danh sách domain cho phép của Entra. Điều này CHƯA được xác minh end to end (chưa kiểm Entra có đi qua cổng `ENABLE_SIGNUP` không).

## Migration ee 0004 (không đảo ngược)

XÓA CỨNG mọi `WorkspaceMemberInvite` và `ProjectMemberInvite` (kể cả đã accepted/xóa mềm) để đăng nhập không tạo workspace member từ lời mời cũ. Mất lịch sử lời mời; rollback là no-op. Sao lưu DB trước khi migrate nếu cần giữ.

## Giới hạn đã biết

- Không có cờ ẩn: user được thêm hiện trong danh sách thành viên workspace và thấy/join được mọi project public khác (project cần kín thì đặt Private khi tạo).
- Modal thêm member của plugin là bản sao; upstream đổi modal gốc không tự lan sang.
- Shadow route và bản vá `ProjectBasePermission` phụ thuộc cấu trúc core; test sẽ lỗi khi merge upstream. Chạy `scripts/check-core-allowlist.sh` sau mỗi lần merge.
- Còn nguyên từ core: workspace Admin chỉ được thêm làm project Admin; project Admin không phải workspace Admin không cấp được role 20.
- Không phân biệt "workspace admin suspend" với "hết project" (cùng `is_active=False`): project admin có thể thêm lại user từng bị suspend, và kích hoạt lại hàng workspace Admin bị suspend sẽ đặt role theo bảng trên.
- User không thuộc project nào thì không thấy workspace.
- Các lối vào mời khác trên web (route /invitations, /workspace-invitations) chỉ còn là phần thừa giao diện, backend trả 410.
