# EE Custom Fields — Design

Ngày: 2026-10-26 · Trạng thái: **chờ duyệt** · Mục "Quyết định của tôi" là phần tôi tự chọn, chưa được xác nhận.

## 1. Mục đích

Admin/PM của một project cần lưu thêm thông tin có cấu trúc trên work item (vd Bug có "Mức độ ảnh hưởng", "Môi trường"; Story có "Story point thực tế") mà Plane chưa có. Mỗi **work item type** trong project có bộ field riêng, không phải một bộ chung cho mọi type.

Thực hiện như **plugin EE**: code mới nằm trong thư mục `ee`, core chỉ thêm vài điểm nối nhỏ.

## 2. Phạm vi

### Goals
- Bật/tắt custom fields **theo từng project**.
- Admin/PM project thêm, sửa, ẩn/xóa, sắp xếp field **theo từng work item type** trong project đó.
- Thành viên có quyền sửa work item nhập/sửa giá trị trong trang chi tiết work item.
- Tắt tính năng hoặc xóa field không làm mất dữ liệu giá trị cũ (soft delete).

### Non-goals (v1)
- Field dùng chung cho mọi type, hoặc cấp workspace.
- Hiển thị cột/lọc/group by/sắp xếp theo custom field ở list, kanban, view; export; analytics.
- Public API `/api/v1`, webhook, import/migrate từ Jira.
- Hiện thay đổi giá trị trong activity feed của core.
- Field công thức, field tính toán, quan hệ giữa các field (phụ thuộc/điều kiện).

### Anti-goals
- Sửa model/serializer/view của core để mang theo custom field.
- Làm hỏng work item hiện có hoặc làm chậm API work item khi tính năng tắt.

## 3. Ràng buộc

- Core đã có `IssueType`, `ProjectIssueType`, `Issue.type`, `Project.is_issue_type_enabled` (model sẵn, chưa có logic/UI). Custom field **tham chiếu `IssueType`**, không tạo lại khái niệm type.
- Checkout `preview` **chưa có** khung EE (`plane/ee`, `apps/web/ee`, `deployments/ee/core-allowlist.txt`, settings EE); khung này đang ở nhánh `etc-dev-migrate`. Spec giả định làm trên nền đó (xem câu hỏi mở Q1).
- Mọi điểm nối vào core phải nằm trong allowlist.
- Chỉ dùng `docker-compose.yml` / `-local` / `-test` khi chạy thử.

## 4. Mô hình dữ liệu (Django app `plane.ee.custom_fields`)

Không thêm cột vào bảng core. Dùng `ProjectBaseModel`/`BaseModel` của core (soft delete, audit).

| Model | Cột chính |
|---|---|
| `CustomFieldSetting` | `project` (1-1), `is_enabled` |
| `CustomField` | `project`, `issue_type` (FK IssueType), `name`, `description`, `field_type`, `is_required`, `is_multi`, `default_value` (JSON), `settings` (JSON), `sort_order`, `is_active` |
| `CustomFieldOption` | `field`, `name`, `color`, `sort_order`, `is_default`, `is_active` |
| `CustomFieldValue` | `issue`, `field`, `project`, `value_text`, `value_number` (decimal), `value_boolean`, `value_datetime`, `value_uuid` (member), `value_option` (FK option) |

- Ràng buộc: `CustomField` unique `(project, issue_type, name)` khi chưa xóa. `CustomFieldValue` single-value: unique `(issue, field)`; multi-value: nhiều dòng cùng `(issue, field)`.
- Giá trị lưu ở **cột có kiểu** (không nhét JSON) để sau này lọc/index được mà không phải migrate lại dữ liệu.
- `field_type` v1: `text`, `textarea`, `number`, `boolean`, `date`, `datetime`, `url`, `select`, `multi_select`, `member`, `multi_member`.
- `issue_type` của field phải thuộc `ProjectIssueType` của project (validate ở serializer).

## 5. Hành vi

- **Bật tính năng**: project admin (và workspace admin) bật `CustomFieldSetting.is_enabled`. Tắt thì UI và endpoint giá trị ẩn/trả rỗng, dữ liệu giữ nguyên.
- **Quyền**: định nghĩa field và option — project admin (role 20). Đọc giá trị — mọi thành viên project. Ghi giá trị — member trở lên (role ≥ 15), guest chỉ đọc.
- **Work item không có type** (`Issue.type` null): không hiện custom field.
- **Đổi type của work item**: giá trị của field không thuộc type mới được **giữ lại trong DB nhưng ẩn**; đổi lại type cũ thì hiện lại.
- **Field bắt buộc**: chỉ ép khi lưu qua endpoint giá trị của EE; không chặn tạo/sửa work item của core. *(Hệ quả: tạo work item xong mới điền; cần xác nhận ở Q3.)*
- **Xóa field**: soft delete định nghĩa; giá trị giữ nguyên nhưng không còn trả ra. **Xóa option đang dùng**: đánh dấu `is_active=False`, giá trị cũ vẫn hiển thị.

## 6. API (đặt dưới `plane/ee/urls`, tiền tố `api/workspaces/<slug>/projects/<project_id>/`)

- `GET|PATCH custom-fields/settings/`
- `GET|POST custom-fields/` (lọc `?issue_type_id=`), `GET|PATCH|DELETE custom-fields/<id>/`
- `POST custom-fields/reorder/`
- `GET|POST custom-fields/<id>/options/`, `PATCH|DELETE .../options/<option_id>/`
- `GET|PUT issues/<issue_id>/custom-field-values/` — PUT nhận `{field_id: value}`, upsert hàng loạt trong một transaction.

Frontend lấy giá trị bằng **request riêng** này, nên **không sửa serializer của work item**. Đổi lại phải trả thêm một request khi mở chi tiết work item.

## 7. Frontend (`apps/web/ee/custom-fields`)

- Service + MobX store (đặt theo pattern store hiện có).
- Trang **Project Settings → Custom fields**: chọn work item type → danh sách field của type đó → thêm/sửa/sắp xếp (kéo thả), quản lý option cho `select`.
- Ô nhập trong **sidebar chi tiết work item**, mỗi `field_type` một editor.
- i18n qua `packages/i18n` (theo skill `translate`).

## 8. Điểm nối vào core (đề xuất, đều nhỏ)

1. Settings EE thêm `plane.ee.custom_fields` vào `INSTALLED_APPS`.
2. `plane/urls.py`: include `plane.ee.urls` khi app EE được cài.
3. Web: route trang settings (file route mỏng trỏ sang component EE) + mục menu "Custom fields" trong project settings.
4. Web: một slot trong `issues/issue-detail/sidebar.tsx` để render section custom fields.
5. Migration của EE phụ thuộc migration core mới nhất (hiện `0124`).

Không điểm nối nào chạm model, serializer hay view của core.

## 9. Quyết định của tôi (cần bạn kiểm)

- Field **bắt buộc theo type**, không có field "áp cho mọi type".
- Giá trị **cột có kiểu**, mirror cách làm property của EE gốc, không dùng JSON.
- Không sửa serializer core, chấp nhận thêm 1 request.
- Giữ giá trị khi đổi type, chỉ ẩn.
- Danh sách field type v1 như ở mục 4 (không có `decimal` riêng, `number` dùng decimal).
- Bỏ activity feed, cột list view và lọc khỏi v1.

## 10. Phân giai đoạn

1. **Backend nền**: app, model, migration, quyền, API định nghĩa + settings, test.
2. **Backend giá trị**: endpoint giá trị, validate theo `field_type`, bắt buộc, test.
3. **Frontend cấu hình**: service, store, trang settings.
4. **Frontend nhập giá trị**: sidebar chi tiết work item, editor theo kiểu.
5. **Kiểm thử end-to-end trong browser** (UI work item types trước đây chưa từng chạy thật; không báo "hoạt động" khi chưa chạy).

## 11. Câu hỏi mở

- **Q1.** Spec này làm trên nền `etc-dev-migrate` (có sẵn khung EE + plugin work item types)? Nếu không, giai đoạn 0 phải dựng khung EE trước.
- **Q2.** Work item types hiện đã có UI chọn type trên work item chưa, hay custom fields phải tự xử lý trường hợp type null?
- **Q3.** Field "bắt buộc" có cần chặn lúc **tạo** work item không (cần sửa core), hay chỉ cảnh báo/ép lúc sửa như đề xuất?
