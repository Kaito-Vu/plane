# Work Item Types (Scrum/Agile) — Thiết kế (rev 3)

Ngày: 2026-10-01 · Trạng thái: chờ duyệt · Đã qua hội đồng review (Jira, Azure DevOps, kiểm chứng code, UX/toàn vẹn/bảo mật) và đối chiếu tài liệu chính thức.

## Mục tiêu
Khi tạo work item, người dùng chọn **work item type** chuẩn Scrum/Agile, mỗi type có icon và màu. Mỗi **project** chọn process **Scrum** hoặc **Agile**. Admin tạo/sửa/xoá type tuỳ biến. Quan hệ cha-con bị ràng buộc theo `level`. Làm dưới dạng **plugin** theo khuôn `ee/` của fork, tối thiểu chạm core.

## Ngoài phạm vi
Custom properties theo type; scheme dùng chung nhiều project; `ProjectIssueType.level`; migrate dữ liệu cũ hàng loạt; Impediment/Issue của ADO (xem quyết định 2); route `/epics/` và màn Epics riêng (xem quyết định 5).

## Hiện trạng đã xác minh trong repo
- Schema có sẵn: `IssueType` (`level` là `FloatField`), `ProjectIssueType` (có `deleted_at`), `Issue.type` (SET_NULL, related_name `issue_type`), `DraftIssue.type`, `Project.is_issue_type_enabled` (bật/tắt qua PATCH project sẵn có). **Không cần migration.**
- `IssueCreateSerializer` (`__all__`) nhận `type`, không nhận `type_id`; `DraftIssueCreateSerializer` thiếu `type_id`. Public API (`api/serializers/issue.py`) có `type_id` nhưng `queryset=IssueType.objects.all()` (nhận type workspace khác) và tự gán type mặc định khi tạo.
- Read path không trả `type_id`: `IssueSerializer.Meta.fields` và `.values(...)` (`app/views/issue/base.py:187/452/884`, `sub_issue.py:159`).
- `getIssueTypeIdOnProjectChange` là stub (`issue-modal/provider.tsx:47`); `issue-type-switcher.tsx` chỉ render identifier.
- Web CE **không có route/màn Epics riêng**; `browse/[workItem]/page.tsx:71` chọn service EPICS khi `issue.is_epic` truthy, nhưng backend không có `/epics/`.
- `IssueManager` (`db/models/issue.py:92`) có 190 lần dùng `issue_objects`/30 file; delete-guard (state, estimate) và `project total_issues` dùng `Issue.objects`.
- Guard `check-core-untouched.sh` chỉ so **tên file**.

## Quyết định thiết kế
1. **Plugin-first**: `apps/api/plane/ee/work_item_types/`, `apps/web/ee/work-item-types/`. Seam core ghi vào `core-allowlist.txt`.
2. **Process theo project (Scrum | Agile)**. Type tạo ở workspace, dùng chung khi trùng tên; project chọn process thì được gán đúng bộ type. Tên type unique theo workspace nên các type chung chỉ tạo một lần.

   | Level | Dùng chung | Chỉ Scrum | Chỉ Agile |
   |---|---|---|---|
   | 4 | Epic | | |
   | 3 | Feature | | |
   | 2 | Bug | Product Backlog Item (mặc định) | User Story (mặc định) |
   | 1 | Task | | |
   | 0 | Sub-task* | | |

   Nguồn: Microsoft Learn (scrum-process, agile-process-workflow, organize-backlog, link-type-reference). \*Sub-task là mở rộng ngoài chuẩn ADO (theo yêu cầu; giống Jira). Số level là cách đánh số của Plane. **Bug ở level 2** tương ứng chế độ "Bug như Requirement" của ADO (ADO còn cho Bug như Task). **Impediment (Scrum) / Issue (Agile) bỏ khỏi preset**: ADO đặt chúng ngoài cây phân cấp, nối bằng link Related, không dùng Parent-Child; admin có thể tạo type tuỳ biến nếu cần.
   - Process của project **suy ra từ type đã gán** (có PBI → Scrum, có User Story → Agile), không thêm cột/bảng. Đổi process chỉ cho phép khi type riêng của process cũ chưa có issue dùng hoặc kèm `migrate` sang type tương ứng.
   - Preset lưu `external_source="plane-work-item-types"`, `external_id=<key>`; UI dịch tên theo key (tái dùng `locales/*/work-item-type.json`); type tuỳ biến hiển thị nguyên văn. Preset hệ thống không xoá được và không đổi `level`. Seed idempotent (lock + `get_or_create` theo `(workspace, external_id)`).
3. **Quy tắc phân cấp** (Jira "cha cao hơn con"; ADO cây Parent-Child):
   - `child.level < parent.level`. Epic (`is_epic`) không có cha. Type `level=0` bắt buộc có cha, cha có `level ∈ {1, 2}` (không trực tiếp dưới Epic/Feature; khớp Jira). Mỗi issue một cha; cấm chu trình (kiểm tra tổ tiên).
   - Đổi type: validate cả cha và con trực tiếp; **item đang có con không được đổi thành Sub-task** (Jira); Epic chỉ đổi sang type khác khi không còn con.
   - Chỉ validate khi `type`/`parent` **thay đổi**; sửa field khác không bị chặn vì dữ liệu cũ. `level` so sánh bằng int.
4. **Type mặc định** theo project (`ProjectIssueType.is_default`: PBI hoặc User Story). Tạo issue không chọn type → server **ghi type mặc định** (không null) — thống nhất app serializer, draft→issue, public API. Issue cũ `type=null` coi là mặc định lúc đọc.
5. **Epic là một work item type bình thường — KHÔNG sửa `IssueManager`, KHÔNG thêm route `/epics/`.** Epic hiện trong list thường (lọc bằng filter Type), nằm được trong cycle/module, được tìm/chọn làm cha, tính vào đếm/progress như mọi issue. Lý do:
   - Khớp Plane Cloud từ 2026-05 ("Epics is becoming a work item type": hiện trong Work Items list, lọc theo Type, thêm được vào cycle/module) và khớp ADO/Jira (vẫn hiện Epic).
   - Web CE không có màn Epics; ẩn Epic sẽ khiến Epic không truy cập được.
   - Tránh toàn bộ rủi ro của sửa manager: lệch số cycle (`cycle/base.py:115`), đường lách module (`module/issue.py:264`, `api/views/module.py:723`), `cycle_transfer_issues.py:435`, Epic không bị auto-archive/close, thêm LEFT JOIN toàn cục, 404 cho detail/relation/search/parent-picker.
   - Cách giữ web trên luồng work item chuẩn: API **không trả `is_epic`** (chỉ `type_id`), nên `issue.is_epic` undefined và `browse/[workItem]/page.tsx` dùng service ISSUES. Web biết một type là Epic qua store type của plugin. Ghi chú: cần xác nhận khi triển khai không còn nơi nào của web gọi `/epics/`.
   - Hệ quả chấp nhận: không có màn/bố cục chuyên biệt cho Epic (như bản Plane cũ). Có thể bổ sung sau bằng filter Type=Epic được lưu thành view.
6. **Quyền**: workspace admin CRUD type (màn ở Workspace Settings); project admin gán/bỏ gán type, chọn process, bật/tắt tính năng (tab Project Settings). Member/guest chỉ đọc. 403 rõ nghĩa; UI ẩn nút theo quyền. Khác Plane Cloud (project admin tạo type) là lựa chọn của fork.
7. **Type inactive / bỏ gán**: chỉ chặn tạo mới và chuyển sang type đó; issue cũ vẫn giữ và hiển thị (badge kèm nhãn "Đã tắt"); sửa issue cũ không bị chặn khi `type` không đổi.

## Backend (`plane/ee/work_item_types/`)
**API** (mount trong `plane/ee/urls.py`; mọi truy vấn lọc theo `workspace__slug`/`project_id` từ URL):
- Workspace: CRUD type; ≤50 type/workspace; throttle; tên unique không phân biệt hoa thường (validate trong `select_for_update`, không migration). `logo_props` validate chặt: `icon.name` thuộc whitelist icon hiện có, màu `^#[0-9a-fA-F]{6}$`, từ chối khoá lạ, giới hạn kích thước; cảnh báo contrast <4.5:1.
- **Xoá type**: `DELETE ?migrate_to=<type_id>` (cùng/tương thích level, `transaction.atomic`, bulk update `Issue.type`). Không có issue dùng (đếm cả archived/draft/soft-deleted) thì xoá thẳng (soft-delete); không migrate được → 409 kèm số lượng; type mặc định không xoá được.
- **Đổi `level`**: cấm khi type đã có issue (409).
- Project: chọn process (gán bộ type), gán/bỏ gán type (bỏ gán type đang dùng → 409), đặt default; bật/tắt dùng PATCH project sẵn có.
- **Đổi type của issue**: endpoint riêng; vi phạm → 400 kèm danh sách con/cha xung đột.

**Validation (`validation.py`)** `validate_work_item_type(project_id, type, parent, instance=None)`:
- type: `ProjectIssueType` của project, `is_active`, `deleted_at is null`, thuộc workspace của project; parent: `Issue.objects.filter(pk=parent, project_id=project_id)`. Lỗi dùng **thông báo chung** (chống IDOR). Siết cả public API.
- Hook `pre_save` của `Issue` đăng ký trong `EeConfig.ready()` (không sửa core), raise `rest_framework.exceptions.ValidationError` → 400. Phủ create/partial_update, draft→issue, public API.
- `bulk_update` bỏ qua `save()`/signal ⇒ gọi validate tường minh ở `app/views/issue/sub_issue.py:236`, validate từng bản ghi.
- `select_for_update` trên type liên quan khi tạo/đổi. Chuyển issue giữa project: map type cùng tên, nếu không có thì về mặc định.

## Seam trong core (thêm vào `core-allowlist.txt`)
| File | Thay đổi |
|---|---|
| `apps/api/plane/app/serializers/issue.py` | field `type_id` (ghi + đọc) |
| `apps/api/plane/app/serializers/draft.py` | thêm `type_id` |
| `apps/api/plane/api/serializers/issue.py` | thu hẹp queryset `type_id`; gọi validate |
| `apps/api/plane/app/views/issue/base.py`, `sub_issue.py` | `type_id` trong `.values`; validate bulk gán sub-issue |
| `apps/api/plane/app/views/workspace/draft.py` | nhận `type_id` ở `create_draft_to_issue` |
| `issue-modal/provider.tsx`, `issue-modal/components/default-properties.tsx` | hook plugin / `<IssueTypeSelect>` |
| `issue-type-switcher.tsx`, `issue-layouts/{list,kanban,spreadsheet}/block*`, `issue-identifier.tsx`, `peek-overview/*` | badge icon + đổi type |
| `apps/web/app/routes/extended.ts` (seam chuẩn, đang rỗng), `packages/constants/src/settings/project.ts` + settings workspace | tab Work item types |
| `packages/types/*`, `packages/i18n/src/locales/*` | kiểu `TIssueType`, chuỗi i18n |
| `deployments/ee/core-allowlist.txt` | thêm các đường dẫn trên |

Không còn sửa `db/models/issue.py`, search, relation, cycle, module, analytics. Cần thêm filter **Type** vào bộ lọc work item (rich filters) để lọc Epic — xác định điểm gắn khi lập plan.

## Frontend (`apps/web/ee/work-item-types/`)
- `IssueTypeSelect`: dropdown icon+màu; khi đã chọn cha, type không hợp lệ **hiện mờ kèm tooltip lý do**; parent picker lọc cha theo level hợp lệ. Nhớ type gần nhất theo project (localStorage, try/catch). Tạo sub-issue nhanh từ cha: tự chọn type theo level liền dưới (Epic→Feature, Feature→PBI/Story, Story→Task, Task→Sub-task), vẫn đổi được.
- `IssueTypeBadge`: icon + `aria-label`/tooltip tên type (không dựa riêng vào màu); type tắt kèm nhãn.
- Tải type lỗi hoặc project chưa bật → ẩn select, không chặn tạo issue; đổi type lỗi → toast, giữ giá trị cũ.
- Store MobX theo project; Workspace Settings (CRUD, empty state + "Tạo từ preset"); Project Settings (chọn Scrum/Agile, gán type, bật/tắt). i18n `en`, `vi-VN` trước; locale khác theo skill `translate`.

## Kiểm thử
- pytest `tests/unit/ee/work_item_types/`: ma trận cha/con cho cả hai process (Task dưới Story/PBI ✔, Story dưới Feature ✔, Sub-task dưới Epic ✘, Epic có cha ✘, Sub-task không cha ✘, chu trình ✘, item có con đổi thành Sub-task ✘); chỉ validate khi thay đổi; bulk sub-issue; draft→issue; public API; **IDOR** (type/parent workspace/project khác, thông báo chung); xoá + `migrate_to`; cấm đổi level khi đang dùng; đổi process; quyền (guest/member/project admin/workspace admin); validate `logo_props`; seed idempotent/đồng thời; Epic trong cycle/module/list vẫn được đếm.
- Unit test frontend: lọc type hợp lệ, mặc định theo level.
- `check-core-untouched.sh` xanh.

## Rủi ro đã biết
- Epic lẫn trong list/board/thống kê (chủ đích): người dùng cần filter Type để tách; cân nhắc view lưu sẵn "Epics".
- Không trả `is_epic` làm web đi luồng ISSUES: cần grep xác nhận không còn gọi `/epics/`; nếu có chỗ phụ thuộc `is_epic`, bổ sung cờ riêng thay vì dựng route Epics.
- Suy ra process từ type đã gán: nếu admin gán lộn cả PBI và User Story thì process không xác định → UI báo trạng thái "Tuỳ chỉnh". Nếu thấy mong manh, thêm bảng `ee` riêng (có migration của plugin) ở bước plan.
- Allowlist theo tên file không chặn sửa nội dung rộng ở file seam; review PR phải kiểm tay.
- Jira: trang "delete/move type" của Atlassian trả 404 lúc tra; quy tắc đổi/xoá type dựa trên trang thay thế và tìm kiếm.
