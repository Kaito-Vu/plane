# Thiết kế: thêm thành viên theo project, bỏ lời mời workspace (v2, đã qua review)

Trạng thái: CHỜ CHỦ SẢN PHẨM DUYỆT. Chưa viết code.
Nguồn: hội đồng 4 chuyên gia (backend, frontend/UX, bảo mật, tối thiểu hóa core) + 2 reviewer (đối kháng, builder), đọc code ngày 2026-11-04.
Quyết định của chủ sản phẩm (2026-11-04): xem mục 3, đánh dấu [CSP].

## 1. Mục tiêu và ngoài phạm vi

Mục tiêu

1. Không còn bước mời user vào workspace. Project admin thêm user vào project, user đăng nhập thấy workspace chứa project đó.
2. Thêm vào project chỉ chấp nhận user ĐÃ tồn tại. Không mời email lạ.
3. Công tắc god-mode bật/tắt "mời user ngoài hệ thống"; mặc định TẮT (dùng Entra: mọi người vào qua provider).
4. Sửa core tối thiểu; logic nằm ở plugin (`apps/api/plane/ee`, `apps/web/ee`).

Ngoài phạm vi

- Không gỡ model `WorkspaceMember` (hơn 88 chỗ trong core dựa vào nó), không thêm cờ "ẩn".
- Không tìm/tạo sẵn user trong thư mục Entra (Graph). User phải đăng nhập Entra một lần trước khi được thêm [CSP].
- Không đổi luồng SSO hiện có.

Phản mục tiêu: user được thêm vào project mà lại tạo được project, hoặc còn đường vào workspace bằng lời mời, thì coi như hỏng dù chạy đúng.

## 2. Hiện trạng (đã đọc code)

- `WorkspaceMember(is_active, role 20/15/5)` là cổng của permission, danh sách workspace (`UserWorkSpacesEndpoint`) và `ProjectMemberViewSet`.
- `ProjectMemberViewSet.create` (`app/views/project/member.py:80`) gọi `WorkspaceMember.objects.get(...)` trước khi ghi: user chưa có ws member gây 500. Core còn chặn: ws Admin không thể là project 5/15 (`:83`), ws Guest không thể là project 15/20 (`:89`). `partial_update` (`:230-236`) cũng `.get()` ws role của target và người gọi, và chặn project Admin không phải ws Admin cấp role 20 (`:271`).
- Danh sách project (`app/views/project/base.py:129,223`): ws Guest chỉ thấy project mình thuộc; ws Member thấy project mình thuộc VÀ mọi project public (`network=2`, mặc định của project mới); ws Admin thấy hết.
- ws Member (15) hiện tạo được project (`app/permissions/project.py:25-31`).
- Đường tạo `WorkspaceMember` từ lời mời: `app/views/workspace/invite.py:221,297`, `ProjectJoinEndpoint` (`project/invite.py:~252`), `authentication/utils/workspace_project_join.py:21,45,59`, `api/views/invite.py`. `ProjectInvitationsViewset.create` đang hỏng sẵn (`.filter(...).role` trên queryset).
- `plane/urls.py:19-25` include `plane.ee.*` TRƯỚC route core, nên ee shadow được route core mà không sửa file core (tiền lệ: `users/me/`, `sign-in`). API v1 có route thêm member riêng (`api/views/member.py:161`), chưa bị shadow.
- Đã có sẵn: `DISABLE_WORKSPACE_CREATION=1` (`app/views/workspace/base.py:94`); god-mode tạo workspace qua `license/api/views/workspace.py:71-99` và gán ws Admin. `plane/ee/migrations` có 0001-0003 (0003 là migration dữ liệu).
- Với Entra, tài khoản chỉ được tạo ở lần đăng nhập đầu (`complete_login_or_signup`). `authentication/adapter/base.py:108`: khi `ENABLE_SIGNUP=0`, đăng ký mới đòi có lời mời.

## 3. Quyết định thiết kế

D1. Role workspace tự cấp khi thêm vào project: project Admin/Member -> ws Member (15); project Guest -> ws Guest (5). Không tạo ws Admin; không đụng ws Admin sẵn có. Khi kích hoạt lại hàng cũ thì đặt role theo bảng này.
Hệ quả chấp nhận [CSP]: user được thêm thấy và join được mọi project public khác trong workspace (project cần kín thì admin đặt Private khi tạo); user hiện trong danh sách thành viên workspace.

D2. Chỉ ws Admin trở lên được tạo project [CSP]. App API tạo project bằng `@allow_permission([ADMIN, MEMBER], level="WORKSPACE")` trên `ProjectViewSet.create` (`app/views/project/base.py:259`), KHÔNG dùng `ProjectBasePermission`; còn API v1 dùng `ProjectBasePermission`. Vì vậy: (a) shadow `POST workspaces/<slug>/projects/` bằng subclass `ProjectViewSet` yêu cầu ws Admin; (b) vá nhánh POST của `ProjectBasePermission` trong `ee/apps.py:ready()` (tiền lệ `god_mode/access.py`) cho API v1. Chữ ký được kiểm bằng test pytest để upstream đổi là hỏng ngay.

D3. Chỉ super admin (god mode) tạo workspace [CSP]: đặt `DISABLE_WORKSPACE_CREATION=1` (có sẵn, không code) và dùng endpoint god-mode hiện có. Ghi vào `.env.prod.example` và tài liệu vận hành. Không shadow `POST workspaces/`.

D4. Backend, 0 file core. Trong `plane/ee/project_members/`:

- Hàm dịch vụ `provision_workspace_member(workspace, user, project_role)`: một `transaction.atomic`, khóa hàng `WorkspaceMember` TRƯỚC (cùng thứ tự với deprovision), idempotent, không hạ role đang có (trừ khi kích hoạt lại, theo D1).
- `ProjectMemberViewSet` con, shadow route `workspaces/<slug>/projects/<id>/members/` (create, partial_update).
- `create`: mọi `member_id` phải là User tồn tại, `is_active`, không bot. Sai một người thì trả 400, mã `USER_NOT_ELIGIBLE`, cùng một dạng lỗi cho "không tồn tại" và "không đủ điều kiện", không ghi gì. Sau đó cấp ws member rồi gọi `super().create()`.
- Giới hạn còn nguyên từ core, ghi rõ trong tài liệu: ws Admin chỉ thêm được làm project Admin (`member.py:83`); project Admin không phải ws Admin không cấp được role 20 (`:271`). `partial_update` chỉ nâng ws role lên 15 khi cần.
- Shadow cả route thêm member của API v1 (`ee/api_urls.py`) dùng cùng hàm dịch vụ, nếu không khóa API vẫn qua mặt.

D5. Gỡ khi hết project [CSP]: khi user không còn `ProjectMember` active nào trong workspace, không phải ws Admin và không phải `Workspace.owner` thì tắt `WorkspaceMember` (`is_active=False`). Cơ chế:

- `post_save` trên `ProjectMember` khi `is_active=False` (bắn ở `destroy`, `leave`, API v1 delete vì chúng dùng `.save()`), gọi hàm `deprovision_if_orphan`.
- Task định kỳ (celery beat, `ee/tasks.py`) đối soát toàn bộ: là cơ chế chính, vì xóa mềm project, `bulk_update`, `queryset.update` không bắn signal. Việc project bị xóa mềm làm user mất project cuối cũng được sweep bắt.
- Receiver `post_save` còn gọi `provision_workspace_member` cho hàng active (lưới an toàn cho đường `.save()` khác); bulk write không bắn signal nên bước chặn ở view vẫn bắt buộc.
- Giới hạn đã biết: không phân biệt được "ws admin suspend" với "hết project" (cùng `is_active=False`), nên project admin có thể thêm lại user từng bị ws admin suspend. Chấp nhận ở v1; marker trong ee là nâng cấp khi cần.
- User chưa thuộc project nào: hành vi hiện tại, không thấy workspace [CSP].

D6. Đóng mọi đường mời (khi công tắc D8 TẮT):

- Shadow trả 410, mã `INVITES_DISABLED`: tạo/join lời mời workspace, bulk accept, `ProjectInvitationsViewset.create`, `ProjectJoinEndpoint`, endpoint mời của API v1.
- Migration dữ liệu ee 0004: XÓA CỨNG mọi lời mời workspace/project (kể cả đã accepted nhưng chưa replay) để `workspace_project_join.py` không tạo hàng khi đăng nhập. Mất lịch sử lời mời (lựa chọn của tôi).
- Yêu cầu vận hành: `ENABLE_SIGNUP=0` đòi lời mời mới đăng ký được; xóa hết lời mời cộng `ENABLE_SIGNUP=0` thì không ai mới vào được. Với Entra, chạy `ENABLE_SIGNUP=1` cùng danh sách domain cho phép của Entra (cần xác minh Entra có đi qua cổng `ENABLE_SIGNUP` không, ở bước lập kế hoạch).

D7. Tìm user: `GET workspaces/<slug>/projects/<id>/members/search/` (đặt trước `members/<pk>/`). Chỉ project Admin của project đó; query tối thiểu 3 ký tự, tối đa 10 kết quả; throttle `30/min`/user; loại inactive, bot, và người đã là member active của project; trả `id, display_name, avatar`, email che một phần (`a***@domain`); serializer riêng, không dùng `UserLiteSerializer`; ghi log truy vấn.

D8. Công tắc god-mode "Cho phép mời user ngoài hệ thống" (`InstanceConfiguration` khóa `ALLOW_EXTERNAL_INVITES`, mặc định TẮT). TẮT: D6 hiệu lực. BẬT: shadow D6 chuyển tiếp xuống core (hành vi cũ, gồm cả lỗi sẵn có). Quy tắc "chỉ user tồn tại" của D4 luôn giữ cho đường thêm trực tiếp. Endpoint đọc/ghi trong `ee/god_mode/`; mục trên trang admin là 1 seam core web (`apps/admin`).

D9. Web (plugin `apps/web/ee/project-members/`):

- Modal thêm member bản mới dùng D7 thay danh sách workspace member; role mặc định Member (15), trần theo role của admin trong project. Header file ghi commit gốc của modal.
- Seam core web (đưa vào `deployments/ee/core-allowlist.txt` cùng PR): (1) `components/project/member-list.tsx` đổi 1 dòng import; (2) `settings/(workspace)/members/page.tsx` ẩn nút mời workspace; (3) trang admin cho công tắc D8. Tránh `routes/core.ts`.
- Chuỗi i18n mới: `en` và `vi-VN` (theo thực hành hiện tại), các locale khác dùng fallback; theo skill `translate`.

## 4. Bất biến

- I1: `WorkspaceMember` chỉ do hàm dịch vụ (hoặc ws admin / người tạo workspace / god-mode) tạo; không bao giờ từ lời mời. Receiver an toàn cũng gọi hàm dịch vụ.
- I2: user đích tồn tại, active, không bot; lỗi 400 `USER_NOT_ELIGIBLE` cùng một dạng.
- I3: actor là Admin của đúng project; project thuộc đúng workspace slug (chống IDOR).
- I4: search bị giới hạn, throttle, trả trường tối thiểu.
- I5: ws role do hàm dịch vụ cấp chỉ là 15 hoặc 5.
- I6: không ai ngoài ws Admin+ tạo được project.

## 5. Kiểm thử (pytest, `apps/api/plane/tests`; phần D5 gọi qua API hoặc hàm, không dựa signal trong fixture)

- Route `members/` (app và v1) phân giải vào view ee; chữ ký `ProjectMemberViewSet.create` và `ProjectBasePermission.has_permission` đúng như mong đợi.
- Thêm user lạ/inactive/bot: 400 `USER_NOT_ELIGIBLE`, không có User mới, không ghi hàng nào.
- Thêm user thật: có `WorkspaceMember` đúng role (15 hoặc 5); workspace xuất hiện trong `UserWorkSpacesEndpoint`; ws Admin target: xác nhận giới hạn core như D4.
- Admin project A không thêm được vào project B (403).
- ws Member không tạo được project (403); ws Admin tạo được.
- Gỡ khỏi project cuối: ws member bị tắt; ws Admin/owner không bị tắt; còn project khác thì không tắt; xóa mềm project rồi chạy sweep thì user mồ côi bị tắt; thêm lại thì bật lại.
- Search: 2 ký tự -> 400; lần gọi thứ 31 -> 429; bot/inactive không xuất hiện; khóa phản hồi đúng danh sách.
- Công tắc TẮT: mọi endpoint mời cũ trả 410, không tạo `WorkspaceMember`; BẬT: chuyển tiếp xuống core. Đăng nhập với lời mời cũ không tạo hàng nào (sau migration 0004).
- Web: unit test cho modal mới (debounce, tối thiểu 3 ký tự, role mặc định) và nút mời workspace bị ẩn.
- Cập nhật các test core đang giả định endpoint mời hoạt động.

## 6. Giới hạn đã biết

- Không có cờ ẩn: user được thêm hiện trong danh sách thành viên workspace và thấy project public khác.
- Modal bản plugin là bản sao; upstream đổi modal gốc sẽ không tự lan sang.
- Shadow route và vá `ProjectBasePermission` phụ thuộc cấu trúc core; test ở mục 5 làm lỗi lộ ra khi merge upstream. Chạy `scripts/check-core-allowlist.sh` sau mỗi lần merge.
- Đồng nghiệp chưa từng đăng nhập Entra chưa thêm được.
- Commit trước các thay đổi đang dở ở `ee/apps.py`, `ee/urls.py`, `ee/auth_urls.py` để diff của tính năng này tách riêng.
