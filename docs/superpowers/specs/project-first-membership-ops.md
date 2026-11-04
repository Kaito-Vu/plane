# Vận hành: thêm thành viên theo project (project-first membership)

Tài liệu ngắn cho người vận hành. Thiết kế đầy đủ: `2026-11-04-project-first-membership-design.md`.

## Hành vi

- Workspace chỉ do super admin (god-mode) tạo, qua endpoint license của god-mode. Cần `DISABLE_WORKSPACE_CREATION=1`: `POST workspaces/` trả 403, god-mode không bị ảnh hưởng. Xem mục "Danh sách kiểm tra khi triển khai": biến môi trường chỉ gieo giá trị cho instance mới.
- Project chỉ do workspace Admin trở lên tạo. Workspace Member tạo project nhận 403 (app API và API v1).
- Vào project: project Admin tìm user ĐÃ tồn tại (`GET workspaces/<slug>/projects/<id>/members/search/`, tối thiểu 3 ký tự, tối đa 10 kết quả, 30 lần/phút/user, email che một phần) rồi thêm. User chưa từng đăng nhập (Entra) thì chưa thêm được: không tìm thấy, và thêm trực tiếp trả 400 `USER_NOT_ELIGIBLE`.
- Khi thêm, hệ thống tự cấp workspace role: project Admin/Member -> workspace Member (15); project Guest -> workspace Guest (5). Role project không nhận diện được cũng bị ép về Guest.
- Hệ thống KHÔNG BAO GIỜ nâng role workspace đang active. Muốn nâng (ví dụ Guest lên Member để làm project Member/Admin) thì workspace Admin phải tự nâng role workspace.
- Gỡ user khỏi project cuối cùng: workspace member của user bị tắt (`is_active=False`), trừ workspace Admin và owner của workspace. Gỡ qua view/`.save()` thì xử lý ngay; còn lại do task định kỳ `ee-sweep-orphan-workspace-members` (celery beat, mỗi giờ phút 0) đối soát toàn bộ, kể cả khi project bị xóa mềm.
- Lưới an toàn: chỉ khi một dòng `ProjectMember` active được TẠO MỚI qua đường `.save()` khác thì receiver mới cấp workspace member. Không có override `partial_update` của ee: đổi role project dùng nguyên hành vi core.

## Công tắc god-mode "External invitations"

- Trang admin app: `/external-invites` (API: `GET/PATCH /api/instances/external-invites/`, khóa `ALLOW_EXTERNAL_INVITES`). Mặc định TẮT.
- TẮT: mọi đường mời (mời/join workspace, bulk accept, mời/join project, mời của API v1) trả 410 `INVITES_DISABLED`, không tạo dòng nào.
- BẬT: các endpoint đó chuyển tiếp xuống core (gồm cả lỗi sẵn có của core). Thêm trực tiếp vào project vẫn chỉ chấp nhận user đã tồn tại. KHÔNG phải khôi phục hành vi cũ nguyên vẹn: user chấp nhận lời mời workspace mà chưa thuộc project nào sẽ bị task đối soát mỗi giờ tắt `WorkspaceMember` (xem mục sweep).

## Danh sách kiểm tra khi triển khai

1. `DISABLE_WORKSPACE_CREATION`: `settings.SKIP_ENV_VAR` mặc định "1" (`plane/settings/common.py`) nên `get_configuration_value` đọc dòng `InstanceConfiguration` trước; `configure_instance` chỉ `get_or_create` dòng đó. Vậy biến môi trường chỉ có tác dụng khi cài mới. Instance đã có: bật trong god-mode (trang Workspace, "Prevent anyone else from creating a workspace") hoặc sửa dòng DB. Kiểm tra: `GET /api/instances/`, trường `is_workspace_creation_disabled` phải là `true`.
2. Trước khi deploy, liệt kê workspace member sẽ bị sweep tắt (xem mục sweep) để báo trước cho người dùng.
3. `ENABLE_SIGNUP` / Entra: xem mục dưới.

## Task đối soát (sweep)

Mỗi giờ (phút 0), `ee_sweep_orphan_workspace_members` tắt mọi `WorkspaceMember` active mà user không phải workspace Admin, không phải owner và không có `ProjectMember` active nào ở project chưa xóa.
- Lần chạy đầu sau khi deploy sẽ tắt hàng loạt các member hiện có nhưng chưa thuộc project nào. Truy vấn liệt kê trước khi deploy (Django shell):

```python
from django.db.models import Exists, F, OuterRef
from plane.db.models import ProjectMember, WorkspaceMember
live = ProjectMember.objects.filter(workspace_id=OuterRef("workspace_id"), member_id=OuterRef("member_id"),
                                    is_active=True, project__deleted_at__isnull=True)
(WorkspaceMember.objects.filter(is_active=True).exclude(role=20).exclude(member_id=F("workspace__owner_id"))
 .annotate(has_live=Exists(live)).filter(has_live=False)
 .values_list("workspace__slug", "member__email", "role"))
```
- Khi `ALLOW_EXTERNAL_INVITES` BẬT, user chấp nhận lời mời workspace mà chưa thuộc project nào sẽ bị tắt trong vòng một giờ.

## Đăng ký / Entra

`ENABLE_SIGNUP=0` đòi lời mời mới đăng ký được (`authentication/adapter/base.py`). Migration `ee 0004` xóa hết lời mời, nên `ENABLE_SIGNUP=0` thì không ai mới vào được. Với Entra, giữ `ENABLE_SIGNUP=1` cùng danh sách domain cho phép của Entra. Điều này CHƯA được xác minh end to end (chưa kiểm Entra có đi qua cổng `ENABLE_SIGNUP` không).

## Migration ee 0004 (không đảo ngược)

XÓA CỨNG mọi `WorkspaceMemberInvite` và `ProjectMemberInvite` (kể cả đã accepted/xóa mềm) để đăng nhập không tạo workspace member từ lời mời cũ. Mất lịch sử lời mời; rollback là no-op. Sao lưu DB trước khi migrate nếu cần giữ.

## Giới hạn đã biết

- Không có cờ ẩn: user được thêm hiện trong danh sách thành viên workspace và thấy/join được mọi project public khác (project cần kín thì đặt Private khi tạo).
- Modal thêm member của plugin là bản sao; upstream đổi modal gốc không tự lan sang.
- Shadow route và bản vá `ProjectBasePermission` phụ thuộc cấu trúc core; test sẽ lỗi khi merge upstream. Chạy `scripts/check-core-allowlist.sh` sau mỗi lần merge.
- Còn nguyên từ core: workspace Admin chỉ được thêm làm project Admin (core chặn ở POST, và ee không đổi); workspace Guest chỉ làm được project Guest. Đã đổi so với core: project Admin không phải workspace Admin KHÔNG cấp được role 20 trên POST (ee trả 400 `ROLE_NOT_ALLOWED`; core vốn chỉ chặn ở PATCH). Modal ẩn các role không hợp lệ theo `workspace_role` của user đích (trả về trong kết quả tìm kiếm).
- Không phân biệt "workspace admin suspend" với "hết project" (cùng `is_active=False`): project admin có thể thêm lại user từng bị suspend, và kích hoạt lại hàng workspace Admin bị suspend sẽ đặt role theo bảng trên.
- User không thuộc project nào thì không thấy workspace.
- Sau khi đổi công tắc god-mode, nút mời ở workspace Settings > Members chỉ đổi sau khi tải lại trang đầy đủ (giá trị được cache theo lần tải trang).
- Tên role Guest/Member/Admin vẫn là tiếng Anh trong vi-VN (hằng số của core).
- Core cho phép thêm một ws Member làm project Admin; chỉ đích là ws Admin và ws Guest bị khóa role.
- Các lối vào mời khác trên web (route /invitations, /workspace-invitations) chỉ còn là phần thừa giao diện, backend trả 410.

## Đăng nhập lần đầu và onboarding

- User phải đăng nhập (Entra) một lần để tồn tại thì mới thêm được. Khi được thêm vào project, hàm cấp workspace member (tạo mới HOẶC bật lại hàng) kiểm tra `Profile` của user: nếu `onboarding_step.profile_complete` đã true thì đặt `is_onboarded=true` và `onboarding_step.workspace_join=true`, để web không đưa user vào /onboarding ở bước "nhờ admin mời" mãi mãi. Không đụng Profile khi hàng workspace đã active sẵn, khi không có Profile, hoặc khi bước profile chưa xong.
- User chưa xong bước profile: vẫn vào onboarding để điền profile. Với bản self-hosted, xong profile thì `components/onboarding/root.tsx` thấy user đã có workspace (`workspacesList.length > 0`) và kết thúc onboarding, vào thẳng workspace.

## Hiển thị và giới hạn bổ sung

- User bị tắt (sweep hoặc gỡ khỏi project cuối) vẫn hiện là hàng "Suspended" và được tính vào chip đếm trong Workspace Settings > Members, và vẫn xuất hiện trong ô chọn project lead (hành vi của core với `WorkspaceMember.is_active=False`).
- Bất kỳ user nào được thêm vào project đều thành workspace Member, và core trả EMAIL ĐẦY ĐỦ của mọi workspace member qua `GET workspaces/<slug>/members/` (`WorkspaceMemberAdminSerializer` cho role trên Guest). Vì vậy việc che email ở ô tìm kiếm chỉ mang tính hiển thị. Giới hạn đã biết, không đổi core.
- Tạo project bởi workspace Admin với `project_lead` là user chưa có hàng workspace sẽ cấp hàng workspace cho user đó, và có thể bật lại một workspace member đang bị suspend.
- Project đã archive vẫn được tính là "còn sống" cho sweep: user mà mọi project đều archive vẫn giữ quyền vào workspace.
- Hạ một workspace Admin không thuộc project nào xuống Member/Guest thì lần sweep kế tiếp tắt `WorkspaceMember` của họ.
- Race hiếm: user tự join một project public đồng thời với việc bị gỡ khỏi project cuối cùng còn lại có thể để lại `ProjectMember` active với hàng workspace không active, và không gì tự sửa. Cách xử lý: thêm lại user qua endpoint thêm member.
- Phần thừa trên web còn trỏ tới lời mời workspace khi công tắc TẮT (chỉ là giao diện, không đổi để giữ sửa core ở mức tối thiểu): `workspace/sidebar/dropdown-item.tsx` (mục "Invite members"), trạng thái rỗng ở trang chủ `no-projects.tsx`, các trang `/invitations`, bước mời team trong onboarding, nút Accept ở `/workspace-invitations` (không có tác dụng nhìn thấy được), và thông báo "liên hệ admin workspace để được mời" ở `not-a-member.tsx` / `workspace-wrapper`.

## Kết quả chạy kiểm thử trực tiếp (chỉ dev)

Lần 1 (backend qua HTTP thật trên API đang chạy, trước các bản sửa vòng 2; code ở commit `6f5250f1e`), ĐẠT:
- bob (ws Member) tạo project nhận 403, ws Admin tạo được (201).
- Search: `q=car` chỉ trả đúng người khớp với email che một phần; `q=ca` trả 400; bot và user inactive không xuất hiện; người không thuộc project nhận 403.
- Thêm user chưa có hàng workspace (role 15): cấp hàng ws, workspace xuất hiện trong `/api/users/me/workspaces/`, user đó không tạo được project; role 5 -> ws Guest.
- Thêm lại -> 400 `ALREADY_MEMBER`; project Admin không phải ws Admin thêm role 20 -> 400 `ROLE_NOT_ALLOWED`; bot / inactive / id không tồn tại -> cùng một 400 `USER_NOT_ELIGIBLE`; project Member không thêm được (403).
- Gỡ khỏi project và `leave` đều tắt hàng ws và workspace biến mất; thêm lại thì bật lại (role được gán lại theo bảng).
- Công tắc TẮT: POST lời mời workspace, POST lời mời project, workspace join, project join, POST `users/me/workspaces/invitations` đều 410 `INVITES_DISABLED`; GET danh sách lời mời vẫn 200. God-mode PATCH bật/tắt được; BẬT thì chuyển tiếp xuống core (POST lời mời workspace 200 và có tạo dòng); TẮT lại -> 410.
- `POST /api/workspaces/` -> 403 "Workspace creation is not allowed" khi `DISABLE_WORKSPACE_CREATION=1`; god-mode `POST /api/instances/workspaces/` -> 201.
- Task `plane.ee.project_members.tasks.ee_sweep_orphan_workspace_members` tắt đúng user mồ côi sau khi project duy nhất của họ bị xóa mềm (lần chạy thứ hai: 0); mục celery beat đã đăng ký mỗi giờ.
- Không có 5xx/traceback trong log API (log của container đầu cho một số bước đầu của lượt chạy bị mất; các phản hồi của chúng không có 5xx).

Lần 2 (web + admin trên trình duyệt thật cùng API, ở commit `28ddbd7c1`), ĐẠT:
- Trang Members tải được (lỗi crash trước đó đã sửa); modal mở với một dòng; gõ "ca" không gửi request và hiện gợi ý 3 ký tự; "car" liệt kê người khớp với email che một phần; thêm xong hiện toast thành công và user xuất hiện không cần tải lại.
- Ma trận role: ws Guest -> chỉ Guest, ws Admin -> chỉ Admin, user thường -> mọi role; project Admin không phải ws Admin không bao giờ được đề nghị Admin, và có thông báo rõ ngay trên dòng khi đích đòi ws Admin.
- Toast dễ đọc, đã dịch cho `ALREADY_MEMBER` / `USER_NOT_ELIGIBLE` / xung đột role, form giữ nguyên lựa chọn; thêm nhiều người cùng lúc chạy đúng.
- Onboarding: user đã xong profile rồi được thêm vào project vào thẳng workspace sau khi tải lại (không còn bước "nhờ admin mời"); user chưa xong profile hoàn tất profile rồi vào workspace.
- Workspace Settings > Members ẩn nút mời khi công tắc TẮT và hiện khi BẬT (cần tải lại trang đầy đủ để thấy thay đổi, vì giá trị được cache theo lần tải trang); trang admin `/god-mode/external-invites` bật/tắt có toast và trạng thái API khớp.
- Chuỗi vi-VN hiển thị tiếng Việt; locale khác dùng tiếng Anh, không lộ khóa thô; không có 5xx/traceback.

KHÔNG chạy trực tiếp: đường Entra / `ENABLE_SIGNUP`; endpoint mời và thêm member của API v1 (chỉ có test tự động); celery worker / email; các bản sửa của đợt cuối này (chỉ có test tự động).

## Rủi ro còn lại

- Route invite của API v1 dạng format-suffix phân giải vào viewset core chưa được chặn công tắc; hiện `create` trả 500 do tham số `format` không mong đợi, không khai thác được.
- Lời mời đã được chấp nhận khi công tắc BẬT nhưng chưa được replay lúc đăng nhập vẫn tạo workspace member sau khi chuyển sang TẮT; việc bật/tắt công tắc không xóa dữ liệu.
- Tìm kiếm khớp email theo chuỗi con (`icontains`); che email chỉ mang tính hiển thị. Giới hạn: tối thiểu 3 ký tự, 30 lần/phút, chỉ project Admin.
- Log của search chỉ ghi metadata (slug, project, actor, độ dài query), không ghi nội dung query.
- POST thêm member chỉ để thêm: member đang active trả 400 `ALREADY_MEMBER` (đổi role dùng PATCH); role 20 cần người gọi là workspace Admin (`ROLE_NOT_ALLOWED`). Thêm lại qua API v1 một member đã bị gỡ vẫn bị core từ chối (ràng buộc unique của serializer core).
