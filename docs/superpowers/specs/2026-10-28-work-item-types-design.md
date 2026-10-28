# Work Item Types (Agile/Scrum) — Design

Ngày: 2026-10-28 · Trạng thái: **chờ duyệt** · Thay thế `2026-10-26-custom-fields-design.md` (custom field nay là một phần của spec này).

Quy ước: mục **"Quyết định của tôi"** (§13) là phần tôi tự chọn, chưa được bạn xác nhận. Mọi chỗ khác là bạn đã nói trong buổi hỏi đáp.

## 1. Mục đích

Hiện Plane chỉ có "issue" đồng nhất, không phân biệt epic với task hay bug với việc thường. Cần phân loại work item theo mô hình Agile/Scrum: mỗi loại có thuộc tính riêng, nằm trong một cây cha–con có luật chặt, và admin/PM cấu hình thêm thuộc tính động cho từng project.

Dự án mới, **chưa có project hay issue nào tồn tại** → không có migration dữ liệu cũ, không có trạng thái "issue chưa có type".

## 2. Phạm vi

### Goals (làm trọn trong một đợt, không chia phase)
- 6 type: **Epic, Feature, User Story, Task, Bug, Sub-task**, bắt buộc chọn type khi tạo issue, ở mọi project.
- Luật cha–con chặt (§3), kiểm tra ở frontend lẫn backend.
- Thuộc tính **cố định** theo từng type (§4) và thuộc tính **custom** (§5) do admin/PM cấu hình.
- Custom attribute ở **hai cấp**: thư viện workspace (khuôn mẫu) và riêng từng project.
- Attribute bắt buộc bị chặn lúc tạo/sửa, ở frontend và backend.
- Hiển thị: chọn cột hiển thị, lọc, group by, lịch sử hoạt động, **gồm cả custom attribute** (§8).
- API public `/api/v1` và bulk tạo cả cây; import hai bước qua staging (§7).
- Khung EE riêng cho fork; code mới nằm trong `ee`, core chỉ thêm điểm nối nhỏ (§10).

### Non-goals
- Type do người dùng tự tạo thêm (chỉ 6 type cố định).
- Đổi type sau khi tạo.
- Workflow/trạng thái riêng theo type; burndown, velocity, báo cáo sprint; cộng dồn effort/giờ từ con lên cha; tự tính điểm ưu tiên (WSJF); Definition of Done có cấu trúc.
- Attribute dạng công thức, tính toán, phụ thuộc điều kiện giữa các field.
- Liên kết đồng bộ giữa attribute workspace và bản sao trong project.

### Anti-goals
- Tồn tại issue mồ côi (vi phạm luật cha–con) trong DB sau bất kỳ luồng nào.
- Sửa model/serializer/view của core nhiều hơn danh sách §10.
- Làm chậm API issue hiện có khi chưa dùng attribute.

## 3. Type và luật cha–con

| Type | Parent được phép | Bắt buộc có cha |
|---|---|---|
| Epic | Epic | Không (type duy nhất tạo được không cần cha) |
| Feature | Epic, Feature | **Có** |
| User Story | Feature | **Có** |
| Task | User Story | **Có** |
| Bug | Task, User Story | **Có** |
| Sub-task | Task, Bug | **Có** |

Hệ quả: muốn có Task phải có Story ← Feature ← Epic. **Phương án "cho phép issue không cha" đã bị loại, không có ngoại lệ.**

- **Type không đổi được** sau khi tạo (cả qua UI lẫn API).
- Bất biến: không bao giờ tồn tại issue (ngoài triage, xem §7) vi phạm bảng trên. Đổi `parent` của issue sau này cũng phải thỏa bảng, và không được gỡ cha của type bắt buộc cha.
- Chống vòng lặp (Epic trong Epic, Feature trong Feature): validate cha không phải con cháu của chính nó.
- Bảng luật là hằng số trong code (type cố định), không lưu DB.

## 4. Attribute cố định (giả định của tôi, bạn chưa duyệt chi tiết)

Attribute cố định do hệ thống seed (`is_system=true`): không xóa, không đổi tên/kiểu; chỉ được xem. Dùng chung engine attribute với custom (cột có kiểu), nên hiển thị/lọc/activity giống nhau.

Danh sách này đã đối chiếu với danh sách bạn gửi (dựa theo field của Azure DevOps Scrum) và với field sẵn có của core.

**A. Field core có sẵn — dùng lại, không tạo mới** (EE chỉ quy định type nào hiện field nào): State, **Sprint = Cycle**, Assignee, Description, Priority, Start Date, Target Date, Attachments. "Due Date" và "Estimate Date" của bạn được gộp vào **Target Date** (cùng nghĩa); "Assignee" ghi trùng 2 lần được tính một.

**B. Field mới do EE tạo** (`is_system=true`, không xóa/đổi tên/đổi kiểu; admin/PM chỉ được chỉnh cờ bắt buộc và với Project Phase thì chỉnh danh sách option):

| Type | Field mới (kiểu) | Bắt buộc mặc định |
|---|---|---|
| Epic, Feature | Acceptance Criteria (rich text), Story Points (số), Business Value (số nguyên), Time Criticality (số), Value Area (select: Business / Architectural), Project Phase (select) | không |
| User Story | như trên | **Acceptance Criteria** |
| Task | Acceptance Criteria (rich text), Original Estimate (giờ), Remaining Work (giờ), Spent Time (giờ) | không |
| Sub-task | Original Estimate (giờ), Remaining Work (giờ), Spent Time (giờ) | không |
| Bug | **Severity** (select: Critical / Major / Minor / Trivial), **Steps to Reproduce**, **Expected Result**, **Actual Result**, **System Info** (đều textarea), Version Found (text), Story Points (số) | Severity, Steps to Reproduce, Actual Result |

**Đơn vị ước lượng (bám Scrum):** Epic/Feature/Story/Bug dùng **Story Points** (đơn vị ước lượng độ lớn tương đối gồm công sức, độ phức tạp, rủi ro; số ≥ 0, không quy đổi ra giờ; giao diện gợi ý dãy Fibonacci cải biên 0,1,2,3,5,8,13,21 nhưng không ép); Task/Sub-task dùng **giờ** (số ≥ 0) với bộ ba Original Estimate / Remaining Work / Spent Time (= Completed Work của Azure DevOps). Business Value và Time Criticality là số ≥ 0, giá trị lớn = ưu tiên cao; hai field này cùng Story Points là đầu vào để PO xếp thứ tự backlog (kiểu WSJF), **hệ thống không tự tính và không cộng dồn từ con lên cha** — nhập tay.

**Đối chiếu với danh sách của bạn — chênh lệch tôi đã xử lý:**
- **Sprint (Cycle) không áp dụng cho Epic và Feature** (khác danh sách của bạn): theo Scrum, chỉ hạng mục hoàn thành được trong một sprint mới vào sprint; Epic/Feature quá lớn, theo dõi bằng Target Date, Project Phase. Xem §6.
- Task/Sub-task **không có** Business Value, Time Criticality, Value Area, Project Phase, Story Points (trong Scrum các field này thuộc Epic/Feature/Story; Task dùng Original Estimate + Spent Time thay cho Story Points). Nếu bạn vẫn muốn có ở Task thì thêm lại, rất rẻ.
- Sub-task **không có** Acceptance Criteria (bạn có liệt kê; tôi bỏ vì Sub-task là bước nhỏ của Task, giữ tiêu chí ở Task).
- Bug: danh sách của bạn thiếu **Severity** (khác Priority của core: Severity là mức ảnh hưởng của lỗi, Priority là thứ tự xử lý) — tôi thêm; "System Info" của bạn thay cho "Môi trường"; giữ thêm Version Found.
- Project Phase: danh sách giá trị mặc định tôi đoán (Initiation / Planning / Execution / Closing), project admin sửa được.
- Story Points không dùng `estimate_point` của core, để khỏi phụ thuộc cấu hình estimate của từng project.

## 5. Attribute custom

**Hai cấp:**
1. **Thư viện workspace** — workspace admin định nghĩa khuôn mẫu theo từng type.
2. **Project** — admin/PM project: (a) *áp dụng* khuôn mẫu workspace, hoặc (b) *tạo mới* attribute chỉ dùng trong project.

**Áp dụng = sao chép.** Sao chép định nghĩa (và option) thành bản riêng của project, **không giữ liên kết**: sửa/xóa khuôn mẫu workspace sau đó không ảnh hưởng project. Trong project, admin/PM được **sửa, ẩn, xóa mềm** bản sao đó.

- Kiểu: `text`, `textarea`, `number`, `boolean`, `date`, `datetime`, `url`, `select`, `multi_select`, `member`, `multi_member`.
- Thuộc tính: tên, mô tả, kiểu, bắt buộc, giá trị mặc định, option (select), thứ tự, active.
- Mỗi attribute thuộc **một type** (vd "Môi trường" của Bug). Unique `(project, type, name)` khi chưa xóa.
- Xóa/ẩn attribute hoặc option đang dùng: giữ giá trị cũ trong DB, ẩn khỏi UI (soft delete / `is_active=false`).
- Đổi **kiểu** của attribute đã có giá trị bị chặn (chỉ ẩn rồi tạo mới).

## 6. Hành vi tạo/sửa work item

- Form tạo: chọn type trước → hiện attribute của type đó (cố định + custom đang active). Chọn cha: chỉ liệt kê issue có type hợp lệ làm cha.
- **Attribute bắt buộc**: frontend báo lỗi ngay trong form; backend trả **400** với danh sách field thiếu/sai. Áp dụng cả lúc sửa (không cho xóa trắng field bắt buộc).
- Giá trị lưu cùng request tạo/sửa issue (một transaction) để không có issue thiếu giá trị bắt buộc.
- **Quy tắc Scrum đi kèm** (tôi đề xuất, §13):
  - **Sprint = Cycle của core.** Chỉ **User Story, Bug, Task, Sub-task** được đưa vào cycle; Epic và Feature bị chặn. Một issue chỉ ở một cycle tại một thời điểm (đúng với core) và cycle chưa xong thì chuyển sang cycle kế bằng thao tác chuyển (carry-over) có sẵn của core. Task/Sub-task nên cùng cycle với Story cha: nếu khác thì **cảnh báo**, không chặn.
  - **Hoàn thành cha cần hoàn thành con:** không cho chuyển issue sang state group *Completed* khi còn con chưa ở *Completed* hoặc *Cancelled*; báo lỗi liệt kê các con còn mở. Mở lại con khi cha đã xong thì cho phép nhưng cha giữ nguyên (chỉ cảnh báo).
  - **Thứ tự backlog = rank thủ công** (`sort_order` của core), không phải Priority; Priority chỉ là nhãn mức khẩn cấp. Backlog của Story/Bug phải sắp theo rank kéo thả.
  - **State mặc định giữ bộ của core** (Backlog, Todo, In Progress, Done, Cancelled), đọc theo Scrum là New, Ready, Committed/In progress, Done, Removed; không thêm state riêng theo type.
  - **Sprint Goal** = mô tả của Cycle; **Definition of Done** ngoài phạm vi (nằm trong mô tả project hoặc cycle).
- **Nhân bản issue**: giữ nguyên type và cha của bản gốc, sao chép giá trị attribute.
- **Xóa issue có con** (bạn đã chốt): **xóa mềm cả cây con** (mọi hậu duệ) trong một transaction, cùng `deleted_at`; khôi phục cha thì khôi phục các hậu duệ có cùng `deleted_at`. **Lưu trữ (archive) issue có con** cũng áp dụng cho cả cây (tôi quyết, để khỏi để lại con mồ côi trên backlog). Cần hộp thoại xác nhận nêu số con sẽ bị xóa/lưu trữ.

## 7. Các luồng tạo ngoài form

Mọi luồng phải qua cùng một hàm validate (type, cha, attribute bắt buộc).

- **API public `/api/v1`**: `type` bắt buộc; `parent` bắt buộc trừ Epic; sai thì 400.
- **Bulk tạo cả cây (API)**: mỗi dòng có `ref` do client đặt và `parent_ref` (trỏ dòng khác trong lô) hoặc `parent_id` (issue đã có). Server xếp thứ tự từ gốc xuống, **một transaction**, lỗi một dòng thì rollback cả lô. Có `?dry_run=true`.
- **Import hai bước (qua staging):**
  - B1 — nạp vào bảng staging; dòng **chưa phải issue thật**, không hiện trong backlog.
  - B2 — màn hình gán cha: liệt kê dòng chưa hợp lệ (thiếu cha, cha sai type, thiếu attribute bắt buộc), cho sửa/ánh xạ hàng loạt. Khi mọi dòng hợp lệ mới bấm Commit → tạo issue thật trong một transaction. Có dry-run.
- **Intake (inbox)** — theo tư vấn của hội đồng (§13 mục 6, 14): intake issue là bản ghi `Issue` ở state triage (core đã loại khỏi backlog). Khi còn **pending/snoozed**, hàm validate chạy ở chế độ *triage*: **cho phép chưa có cha và chưa đủ attribute bắt buộc** (người báo ngoài không biết cây công việc). Người gửi chọn type **Bug** (mặc định) hoặc **User Story**. **Từ chối / đánh dấu trùng**: không cần cha. **Chấp nhận** (ra khỏi triage): validate **đầy đủ** như issue thường — người duyệt bắt buộc chọn cha hợp lệ và điền attribute bắt buộc, nếu không bị chặn.

**Các luồng tạo/đổi issue sẵn có của core** (đều phải qua hàm validate chung; danh sách điểm nối cụ thể chốt khi lập plan):
- **Quick-add** (list/kanban/spreadsheet) và **tạo từ cycle/module**: form inline có thêm chọn type và cha; không có đường tắt bỏ qua.
- **Tạo sub-issue từ trang chi tiết**: cha điền sẵn; chỉ cho chọn type con hợp lệ với type của cha.
- **Draft**: draft chưa phải issue thật (`is_draft`, bị `IssueManager` loại) nên được thiếu cha và attribute; **chuyển draft thành issue** thì validate đầy đủ.
- **Webhook/integration và importer cũ của Plane (GitHub…)**: tắt trong fork này; mọi nhập liệu hàng loạt đi qua bulk-tree hoặc import hai bước.
- **Xóa/lưu trữ**: xóa project/workspace (cascade) không bị coi là vi phạm bất biến. Xóa/bulk delete issue có con thì xóa mềm cả cây con. Auto-archive/auto-close **chỉ xử lý** issue mà mọi hậu duệ đã ở Completed/Cancelled; còn lại bỏ qua và báo lại.

## 8. Hiển thị, lọc, group by, activity

- **Type**: icon + badge ở mọi nơi (list, kanban, spreadsheet, chi tiết, peek); lọc và group by theo type; trang chi tiết hiện breadcrumb cha và cây con.
- **Chọn thông tin hiển thị** (display properties) có thêm mỗi attribute (cố định và custom) như một cột bật/tắt, lưu theo view/người dùng như display properties hiện có.
- **Lọc** theo attribute (cố định và custom) tùy kiểu: text (chứa), number/date (khoảng), boolean, select/multi_select, member.
- **Group by**: type, và attribute kiểu select, member, boolean (kiểu khác không group được).
- **Activity**: thay đổi giá trị attribute và thay đổi cha được ghi vào lịch sử hoạt động.
- Hiệu năng: giá trị lưu ở **cột có kiểu**, index theo `(field, value_*)` để lọc không cần quét JSON.

## 9. Mô hình dữ liệu

Tái dùng model core sẵn có, **không thêm cột vào bảng core**:
- `IssueType` (cấp workspace: `is_epic`, `level`, `is_default`, `logo_props`) — seed 6 type cho mỗi workspace.
- `ProjectIssueType` — gắn cả 6 type vào mọi project lúc tạo project.
- `Issue.type` (FK) và `Issue.parent` (FK) — đã có; type của issue luôn khác null.
- `Project.is_issue_type_enabled` — bỏ qua (luôn bật).

Model mới trong `plane.ee.work_item_types` (dùng `BaseModel`/`ProjectBaseModel` của core: soft delete, audit):

| Model | Cột chính |
|---|---|
| `AttributeTemplate` (workspace) | `workspace`, `issue_type`, `name`, `description`, `field_type`, `is_required`, `default_value`, `settings`, `sort_order`, `is_active` |
| `AttributeTemplateOption` | `template`, `name`, `color`, `sort_order`, `is_default`, `is_active` |
| `Attribute` (project) | `project`, `issue_type`, `name`, `description`, `field_type`, `is_required`, `is_system`, `system_key`, `default_value`, `settings`, `sort_order`, `is_active`, `source_template` (nullable, chỉ để tham khảo, không đồng bộ) |
| `AttributeOption` | `attribute`, `name`, `color`, `sort_order`, `is_default`, `is_active` |
| `AttributeValue` | `issue`, `attribute`, `project`, `value_text`, `value_number`, `value_boolean`, `value_datetime`, `value_uuid`, `value_option` |
| `ImportBatch` / `ImportRow` | staging cho import hai bước: `project`, `status`, dữ liệu dòng, `ref`, `parent_ref`, `errors` |

Ràng buộc: `AttributeValue` single-value unique `(issue, attribute)`; multi-value nhiều dòng cùng `(issue, attribute)`. Attribute cố định được seed vào `Attribute` của từng project (cùng engine). Nhận diện 6 type bằng `IssueType.external_source="agile"` + `external_id=<key>` (xem §13).

Bất biến cha–con được bảo vệ ở 3 lớp: serializer (lỗi 400 thân thiện), signal `pre_save` của EE trên `Issue` (bắt các đường ORM khác), và hàm validate dùng chung cho bulk/import.

## 10. Khung EE và điểm nối vào core

Repo hiện **chưa có** khung EE (`plane/ee`, `apps/web/ee`, allowlist, settings EE). Việc đầu tiên là dựng khung đó cho fork:
- Backend: `apps/api/plane/ee/` (app `work_item_types`), settings EE thêm `plane.ee.*` vào `INSTALLED_APPS`; `plane/urls.py` include `plane.ee.urls`.
- Frontend: `apps/web/ee/` (import qua `@/ee/...`, đã chạy được nhờ alias `@/*`).
- Allowlist `deployments/ee/core-allowlist.txt` liệt kê mọi file core được phép chạm; CI/`pnpm check` không được có thay đổi core ngoài danh sách.
- Migration EE phụ thuộc migration core mới nhất (hiện `0125`).

Điểm nối core dự kiến (đều nhỏ, **cần xác minh từng điểm khi lập plan**):
1. Serializer tạo/sửa issue — app (`plane/app/serializers`) và public (`plane/api/serializers/issue.py`): gọi hàm validate EE, nhận `attribute_values`.
2. Luồng tạo project và tạo workspace: seed 6 type, attribute cố định.
3. Intake: chấp nhận issue bắt buộc có cha.
4. Duplicate issue: sao chép type/cha/giá trị.
5. Web — `IssueModalContext` đã có sẵn hook mở rộng (`issuePropertyValues`, `handlePropertyValuesValidation`, `handleCreateUpdatePropertyValues`, `handleCreateSubWorkItem`) → dùng làm điểm nối chính cho form.
6. Web — slot trong sidebar chi tiết issue, `IssueIdentifier`/`list/block.tsx` (đã nhận `issueTypeId`), menu Project Settings, Workspace Settings.
7. Web/API — display properties, filter, group by: mở rộng schema lưu display properties/filter để nhận khóa `attribute:<id>`.
8. Activity: ghi thay đổi attribute/cha vào pipeline `issue_activities_task`.
9. Cập nhật state (chặn hoàn thành cha khi còn con mở) và thêm issue vào cycle (chặn Epic/Feature, cảnh báo lệch cycle với cha) — cùng gọi hàm validate EE; cần xác minh các view/serializer cycle-issue và state-update, kể cả thao tác kéo thả kanban và bulk update.

## 11. API (tiền tố `api/workspaces/<slug>/…`)

- Workspace admin: `attribute-templates/` (+ `options/`) CRUD, reorder.
- Project: `projects/<id>/attributes/` CRUD + reorder + `apply-template/` (sao chép); `…/options/`.
- Giá trị attribute đi cùng payload tạo/sửa issue (`attribute_values: {attribute_id: value}`) và có `GET issues/<id>/attribute-values/`.
- `POST projects/<id>/issues/bulk-tree/` (§7); import: `projects/<id>/imports/` (tạo batch, tải dòng, sửa dòng, `validate/`, `commit/`).
- `/api/v1`: field `type`, `parent`, `attribute_values`; endpoint bulk tương ứng.

## 12. Quyền

| Hành động | Quyền |
|---|---|
| Định nghĩa/sửa thư viện workspace | Workspace admin |
| Áp dụng khuôn mẫu, tạo/sửa/ẩn/xóa attribute project | Project admin (role 20); PM = project admin (đã xác nhận) |
| Nhập/sửa giá trị attribute | Member trở lên (role ≥ 15); guest chỉ đọc |
| Import, bulk-tree | Member trở lên |

## 13. Quyết định của tôi (cần bạn kiểm)

1. **6 type cố định**, nhận diện bằng `external_source="agile"` + `external_id=<key>` để khỏi thêm bảng; dùng chung `IssueType` của core.
2. **Danh sách attribute cố định ở §4** đã đối chiếu với danh sách của bạn; phần chênh lệch (Task/Sub-task bỏ vài field, Bug thêm Severity, gộp Due/Estimate Date vào Target Date, mặc định bắt buộc) là do tôi quyết, bạn xem lại ở §4.
3. **Story Points** (tên theo lý thuyết Scrum, tương ứng "Effort" của Azure DevOps) là attribute riêng, không dùng hệ estimate của project.
4. **Cha phải cùng project.** Độ sâu tối đa 10 cấp.
5. **Xóa/lưu trữ issue có con áp dụng cho cả cây con** (xóa = chuyển vào thùng rác cả nhánh, bạn đã chốt; lưu trữ cả nhánh là tôi quyết).
6. **Intake** (tư vấn hội đồng): chế độ triage nới lỏng cha và attribute bắt buộc; người gửi chọn Bug hoặc User Story; chấp nhận thì validate đầy đủ; từ chối/trùng thì không cần.
7. **Bất biến cha–con** bảo vệ bằng serializer + signal EE + validate dùng chung, không dùng CHECK ở DB (không biểu diễn được luật liên bảng).
8. **Đổi kiểu attribute đã có giá trị bị cấm.**
9. Group by chỉ cho kiểu select/member/boolean.
10. PM = project admin (role 20) — đã xác nhận.
11. **Độ sâu tối đa 10 cấp tính trên cả chuỗi cha từ gốc**, chỉ để chặn vòng lặp và truy vấn đệ quy vô hạn; chuỗi hợp lệ thực tế chỉ ~6 cấp.
12. **`Issue.type` NOT NULL chỉ ép ở tầng ứng dụng**, không có migration core (không đổi cột core).
13. **Seed**: lúc tạo workspace/project, và thêm management command idempotent `seed_work_item_types` cho workspace/project đã có (kể cả DB dev đã chạy bản cũ). Nếu type cũ lệch thì reset DB dev.
14. **"Triage"** = issue có `state.group == TRIAGE` (đúng định nghĩa `IssueManager` của core). Hàm validate có cờ `triage`: bật thì bỏ qua cha và attribute bắt buộc. Rời triage (chấp nhận) bị chặn cứng nếu thiếu cha hoặc attribute bắt buộc; từ chối/đánh dấu trùng không cần.
15. **Payload dòng bulk-tree/import**: `attribute_values` nằm cùng dòng với `type`, `ref`, `parent_ref`; `ImportRow` lưu dòng dạng JSON; thiếu attribute bắt buộc báo lỗi theo từng dòng.
16. **Giới hạn đã biết của bảo vệ bất biến**: signal `pre_save` không bắt `QuerySet.update/bulk_update/bulk_create`; các luồng bulk của core phải gọi hàm validate chung, và test phải quét các luồng này. Khóa động `attribute:<id>` trong display properties/filter chưa xác minh được core có whitelist cứng hay không → kiểm tra đầu tiên khi lập plan (§10 điểm 7).
17. **Rà theo Scrum** (các điểm lệch danh sách bạn hoặc thêm mới): Epic/Feature không vào sprint (bạn đã xác nhận 2026-10-28); thêm Remaining Work cho Task/Sub-task và Story Points cho Bug; đơn vị story point cho Story-level, giờ cho Task-level; không cộng dồn, không tự tính WSJF; chặn hoàn thành cha khi còn con mở; cảnh báo (không chặn) lệch cycle cha–con; rank thủ công làm thứ tự backlog.
18. Hệ phân cấp Epic → Feature → Story → Task là quy ước của Azure DevOps/SAFe, **không có trong Scrum Guide** (chỉ có Product Backlog Item và Sprint Backlog); spec giữ nguyên theo luật bạn đặt.
19. **Thứ tự lập plan** (không phải phase phát hành): khung EE → type + luật cha–con → attribute cố định/custom → luồng tạo ngoài form → hiển thị/lọc. Tất cả đều bắt buộc cho nghiệm thu.

## 14. Kiểm thử

- Unit backend: ma trận cha–con (đủ 6×6), chống vòng lặp, từng `field_type`, attribute bắt buộc, soft delete, áp dụng khuôn mẫu (sao chép độc lập).
- Contract/API: tạo issue sai luật → 400, bulk-tree rollback, `/api/v1`, quyền theo role.
- Import: dry-run, staging không lộ ra backlog, commit atomic.
- Frontend: form tạo (chọn type → attribute → cha hợp lệ), cột hiển thị, lọc/group by.
- **Chạy thật trên browser** trước khi báo xong (UI work item types trước đây chưa từng chạy thật).
- Chỉ dùng `docker-compose.yml` / `-local` / `-test`.

## 15. Câu hỏi mở

- **Q1.** Chi tiết attribute cố định §4 và cờ bắt buộc mặc định có đúng ý không? *(còn mở)*
- **Q2.** ~~Xóa/lưu trữ issue có con~~ — **đã chốt**: xóa mềm cả cây con.
- **Q3.** ~~Intake~~ — **hội đồng đã tư vấn**, chờ bạn xác nhận phương án §7/§13 mục 6.
- **Q4.** ~~PM~~ — **đã chốt**: PM là project admin.
