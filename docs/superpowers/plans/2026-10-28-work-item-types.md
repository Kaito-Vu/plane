# Work Item Types (Agile/Scrum) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mọi work item có một trong 6 type Agile/Scrum, nằm trong cây cha–con có luật chặt, mang attribute cố định + custom, hiển thị/lọc/group được, tạo hàng loạt được qua API và import hai bước.

**Architecture:** Toàn bộ logic mới nằm trong khung EE của fork (`apps/api/plane/ee/work_item_types`, `apps/web/ee/work-item-types`). Một hàm validate duy nhất `validate_work_item` là cổng cho mọi luồng ghi (form, API v1, bulk-tree, import, intake, duplicate); core chỉ gọi hàm này tại các điểm nối trong allowlist. Giá trị attribute lưu ở cột có kiểu.

**Tech Stack:** Django 4.x + DRF + Celery + pytest (apps/api); React Router + MobX + `@plane/*` packages (apps/web); `pnpm check` / `pnpm check:types` cho frontend (apps/web **không có test runner**, kiểm bằng typecheck + chạy browser thật).

**Spec:** `docs/superpowers/specs/2026-10-28-work-item-types-design.md` (thay `2026-10-26-custom-fields-design.md`). Plan này đọc cùng spec; số mục `§n` ở dưới là mục của spec.

## Global Constraints

- 6 type cố định, khóa nhận diện `IssueType.external_source="agile"`, `external_id ∈ {epic, feature, user_story, task, bug, sub_task}`.
- Bảng cha–con (§3): Epic←Epic|none; Feature←Epic|Feature (bắt buộc); User Story←Feature (bắt buộc); Task←User Story (bắt buộc); Bug←Task|User Story (bắt buộc); Sub-task←Task|Bug (bắt buộc). Type **không đổi** sau khi tạo. Cha cùng project. Độ sâu tối đa 10.
- `Issue.type` NOT NULL chỉ ép ở tầng ứng dụng, **không migration core**. Không thêm cột vào bảng core.
- Triage = `state.group == "triage"`: validate chạy chế độ nới (không cần cha/attribute bắt buộc); rời triage thì validate đầy đủ; từ chối/trùng không cần cha.
- Attribute kiểu: `text, textarea, number, boolean, date, datetime, url, select, multi_select, member, multi_member`. Áp dụng template workspace = **sao chép**, không liên kết. Đổi kiểu attribute đã có giá trị bị cấm. Xóa attribute/option = soft delete, giữ giá trị.
- Story Points: số ≥ 0 (Epic/Feature/Story/Bug). Task/Sub-task: Original Estimate, Remaining Work, Spent Time (giờ, ≥ 0). Business Value, Time Criticality ≥ 0.
- Sprint = Cycle; chỉ User Story/Bug/Task/Sub-task vào cycle. Không cho chuyển cha sang Completed khi còn con chưa Completed/Cancelled. Lệch cycle Task–Story chỉ cảnh báo.
- Xóa issue có con → xóa mềm cả cây cùng `deleted_at`, một transaction, khôi phục theo `deleted_at`. Archive cũng áp cho cả cây.
- Quyền: template workspace = workspace admin; attribute project = project admin (role 20); ghi giá trị ≥ 15; guest chỉ đọc.
- Chạy thử chỉ dùng `docker-compose.yml` / `docker-compose-local.yml` / `docker-compose-test.yml`. Test backend: `docker compose -f docker-compose-test.yml run --rm --build api-tests pytest <path>`.
- Mỗi file core được sửa phải có trong `deployments/ee/core-allowlist.txt` (Task 1).

## Review Focus

1. Issue tạo qua đường không phải serializer (`bulk_create`, `QuerySet.update`) lách luật cha–con → Task 3 có test quét các đường ghi.
2. Xóa cha khi celery `soft_delete_related_objects` chưa chạy (async) → con vẫn hiện tạm thời; Task 7 xóa cây đồng bộ trong transaction.
3. Người báo ngoài (intake) không điền được attribute bắt buộc → Task 7 test intake pending không bị chặn, accept thì bị chặn.
4. Hai người cùng tạo con làm vòng lặp/độ sâu vượt 10 → Task 2 test chống vòng lặp và độ sâu.
5. Đổi cha sang cha cùng type hợp lệ nhưng làm sai cycle/state → Task 7 test đổi cha chạy lại toàn bộ validate.

---

## File Structure

```
apps/api/plane/ee/
  __init__.py, apps.py                       # AppConfig label "ee", ready() nạp signals
  urls.py                                    # gom urls các app con
  work_item_types/
    constants.py                             # TypeKey, PARENT_RULES, SPRINT_TYPES, MAX_DEPTH
    exceptions.py                            # WorkItemValidationError
    registry.py                              # type_key_of, get_type
    hierarchy.py                             # validate_parent, assert_no_cycle, depth_of
    validators.py                            # validate_work_item (cổng duy nhất)
    seed.py + management/commands/seed_work_item_types.py
    models/{attribute,template,value,import_batch}.py
    attribute_catalog.py                     # bảng attribute cố định §4
    value_codec.py                           # coerce_value, write_values, missing_required
    tree_ops.py                              # soft_delete_subtree, restore_subtree, archive_subtree
    scrum_rules.py                           # cycle rule, completion rule
    signals.py                               # pre_save Issue
    bulk_tree.py, importer.py
    serializers/, views/, urls.py
apps/api/plane/tests/{unit,contract}/ee/work_item_types/...
apps/web/ee/work-item-types/{types,services,store,components,pages}/...
deployments/ee/core-allowlist.txt
scripts/check-core-allowlist.sh
```

---

### Task 1: Khung EE + allowlist

**Files:**
- Create: `apps/api/plane/ee/{__init__,apps,urls}.py`, `deployments/ee/core-allowlist.txt`, `scripts/check-core-allowlist.sh`
- Modify (core seam, thêm vào allowlist): `apps/api/plane/settings/common.py` (INSTALLED_APPS), `apps/api/plane/urls.py`
- Test: `apps/api/plane/tests/unit/ee/test_ee_scaffold.py`

**Interfaces:**
- Produces: app label `ee` trong `INSTALLED_APPS`; `plane.ee.urls.urlpatterns` được mount ở `api/` (workspace-scoped) và `api/v1/`; script `scripts/check-core-allowlist.sh` thoát ≠0 nếu `git diff --name-only <base>` chứa file ngoài `plane/ee`, `apps/web/ee`, `docs`, `deployments/ee`, `scripts`, `tests` và ngoài allowlist.

- [ ] **Step 1: Write the failing test** `test_ee_app_installed`: `assert apps.is_installed("plane.ee")`; `test_ee_urls_mounted`: `reverse` một route probe `ee-health` trả 200 với user đã đăng nhập.
- [ ] **Step 2: Run** `pytest plane/tests/unit/ee/test_ee_scaffold.py -m unit` → FAIL (app chưa cài).
- [ ] **Step 3: Implement** AppConfig `EeConfig(name="plane.ee", label="ee")`; thêm `"plane.ee"` vào `INSTALLED_APPS` ở `common.py`; thêm `path("api/", include("plane.ee.urls"))` và `path("api/v1/", include("plane.ee.api_urls"))` vào `plane/urls.py` **trước** các include core tương ứng; thêm route `ee-health`.
- [ ] **Step 4: Viết allowlist** liệt kê đúng 2 file core ở trên; hoàn thành script bằng `git diff --name-only`; chạy `bash scripts/check-core-allowlist.sh preview` → exit 0.
- [ ] **Step 5: Run test → PASS; Commit** `feat(ee): scaffold ee app and core allowlist`.

---

### Task 2: Type registry + luật cha–con (module thuần)

**Files:**
- Create: `ee/work_item_types/{constants,exceptions,registry,hierarchy}.py`
- Test: `tests/unit/ee/work_item_types/test_hierarchy.py`

**Interfaces:**
- Produces:
  - `class TypeKey(str, Enum)` với 6 giá trị §Global.
  - `PARENT_RULES: dict[TypeKey, frozenset[TypeKey]]`, `SPRINT_TYPES: frozenset[TypeKey]`, `MAX_DEPTH = 10`.
  - `class WorkItemValidationError(rest_framework.exceptions.ValidationError)` nhận `code: str, message: str, details: dict | None`.
  - `validate_parent(type_key: TypeKey, parent_type_key: TypeKey | None, *, triage: bool = False) -> None`
  - `assert_no_cycle(issue_id: UUID | None, parent: Issue | None) -> None`; `depth_of(issue: Issue) -> int`
  - `type_key_of(issue_type: IssueType | None) -> TypeKey | None`; `get_type(workspace_id: UUID, key: TypeKey) -> IssueType`

- [ ] **Step 1: Tests** (`@pytest.mark.unit`): tham số hóa đủ **6×6** cặp (type, parent type) so với bảng §3 — hợp lệ chỉ đúng các ô trong `PARENT_RULES`; `test_parent_required_except_epic`: `validate_parent(TypeKey.TASK, None)` raise code `parent_required`, `validate_parent(TypeKey.EPIC, None)` không raise; `test_triage_skips_parent_required`; `test_cycle_rejected` (Epic A→con Epic B, đặt A.parent=B raise `parent_cycle`); `test_depth_over_10_rejected` raise `max_depth_exceeded`.
- [ ] **Step 2: Run** → FAIL (module chưa có).
- [ ] **Step 3: Implement** theo chữ ký trên. `depth_of` đi ngược chuỗi `parent` bằng vòng lặp (không đệ quy SQL), dừng khi vượt `MAX_DEPTH+1`.
- [ ] **Step 4: Run → PASS; Commit** `feat(ee): work item type registry and hierarchy rules`.

---

### Task 3: Seed type + cổng `validate_work_item` + signal

**Files:**
- Create: `ee/work_item_types/{seed,validators,signals}.py`, `management/commands/seed_work_item_types.py`
- Modify (core seam): `apps/api/plane/app/serializers/issue.py` (`IssueCreateSerializer.validate/create`), `apps/api/plane/app/views/project/base.py` (sau `State.objects.bulk_create`), workspace create view (xác minh đường: `grep -n "class WorkSpaceViewSet" apps/api/plane/app/views/workspace/base.py`), `apps/api/plane/bgtasks/workspace_seed_task.py` (project seed)
- Modify: `tests/factories.py` thêm `StateFactory`, `IssueFactory`, `IssueTypeFactory`
- Test: `tests/unit/ee/work_item_types/test_seed.py`, `test_validate_work_item.py`, `tests/contract/app/ee/test_issue_create_types.py`

**Interfaces:**
- Consumes: Task 2.
- Produces:
  - `seed_workspace(workspace: Workspace) -> None`, `seed_project(project: Project) -> None` (idempotent; tạo 6 `IssueType` cho workspace nếu thiếu, 6 `ProjectIssueType` cho project, attribute cố định sẽ do Task 4 gắn thêm).
  - `validate_work_item(*, project: Project, issue_type_id: UUID | None, parent_id: UUID | None, attribute_values: dict | None, instance: Issue | None = None, triage: bool = False) -> None` — raise `WorkItemValidationError`. Kiểm: type tồn tại và thuộc project; type không đổi nếu `instance`; `validate_parent`; parent cùng project; `assert_no_cycle`; `depth_of`. (Attribute bắt buộc được Task 6 nối vào cùng hàm.)
  - signal `pre_save(Issue)` gọi cùng kiểm tra cha–con cho mọi `Issue.save()` trừ khi `state.group == "triage"`.

- [ ] **Step 1: Tests** — seed: `test_seed_workspace_idempotent` (gọi 2 lần vẫn 6 type), `test_seed_project_links_six_types`; validate: `test_missing_type_rejected` (code `type_required`), `test_type_immutable`, `test_parent_other_project_rejected`; contract: `POST /api/workspaces/{slug}/projects/{id}/issues/` thiếu `type_id` → 400 `type_required`; Task không cha → 400 `parent_required`; Task dưới Story → 201; **`test_write_paths_cannot_bypass`**: `Issue.objects.create(...)` Task không cha raise; `Issue.objects.bulk_create` / `QuerySet.update(parent=None)` trên Task: ghi lại hành vi hiện tại bằng test `xfail(strict=True)` nêu rõ ceiling (spec §13.16) và test thứ hai khẳng định mọi view core gọi `validate_work_item`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** seed + validator + signal; gọi `seed_project(project)` ngay sau tạo state ở `ProjectViewSet.create`, `seed_workspace` khi tạo workspace, và trong `workspace_seed_task`; ở `IssueCreateSerializer.validate` gọi `validate_work_item(...)` (đọc `type_id` từ `attrs["type"]`, thêm field `type_id = PrimaryKeyRelatedField(source="type", queryset=IssueType.objects.all())`); `triage` lấy từ `self.context["allow_triage_state"]`.
- [ ] **Step 4: Management command** `seed_work_item_types [--workspace SLUG]` gọi seed cho mọi workspace/project đã có (§13.13). Test gọi command qua `call_command`.
- [ ] **Step 5: Cập nhật allowlist, chạy `check-core-allowlist.sh`, run tests → PASS; Commit** `feat(ee): seed work item types and enforce hierarchy at issue write`.

---

### Task 4: Mô hình attribute + attribute cố định + value codec

**Files:**
- Create: `ee/work_item_types/models/{attribute,template,value}.py` + migration `apps/api/plane/ee/migrations/0001_initial.py` (phụ thuộc `("db", "0125_reset_project_deploy_board_identity")`), `attribute_catalog.py`, `value_codec.py`
- Test: `tests/unit/ee/work_item_types/test_value_codec.py`, `test_attribute_catalog.py`

**Interfaces:**
- Produces models (spec §9): `AttributeTemplate`, `AttributeTemplateOption`, `Attribute`, `AttributeOption`, `AttributeValue` (cột `value_text, value_number, value_boolean, value_datetime, value_uuid, value_option`), dùng `ProjectBaseModel`/`BaseModel`; `Attribute` unique `(project, issue_type, name)` khi `deleted_at IS NULL`; index `(attribute, value_number)`, `(attribute, value_option)`, `(attribute, value_uuid)`.
- `ATTRIBUTE_CATALOG: dict[TypeKey, list[SystemAttrSpec]]` với `SystemAttrSpec(system_key, name, field_type, is_required, options=())` đúng bảng §4 (Story: `acceptance_criteria` bắt buộc; Bug: `severity`, `steps_to_reproduce`, `actual_result` bắt buộc; Project Phase options Initiation/Planning/Execution/Closing; Value Area Business/Architectural; Severity Critical/Major/Minor/Trivial).
- `seed_project` (Task 3) mở rộng: tạo `Attribute(is_system=True, system_key=...)` + option cho mỗi (project, type).
- `coerce_value(attribute: Attribute, raw: Any) -> dict[str, Any]` — trả `{cột_có_kiểu: giá_trị}`, raise `WorkItemValidationError(code="invalid_value", details={"attribute_id": ...})` khi sai kiểu/âm (number ≥ 0 cho các field §Global)/option không thuộc attribute/URL sai.
- `write_values(issue: Issue, values: dict[UUID, Any], *, project: Project) -> None` (upsert trong `transaction.atomic`; multi_* xóa-ghi lại tập dòng); `missing_required(project_id: UUID, issue_type_id: UUID, values: dict[UUID, Any]) -> list[UUID]`.

- [ ] **Step 1: Tests** — mỗi `field_type` một case hợp lệ + một case sai (11×2, tham số hóa); `test_negative_story_points_rejected`; `test_option_of_other_attribute_rejected`; `test_system_attributes_match_spec_table` (so khớp tên + cờ bắt buộc với §4 cho cả 6 type); `test_missing_required_lists_bug_fields`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** models, migration (`makemigrations ee` rồi kiểm `--check`), catalog, codec. **Step 4: Run → PASS; Commit** `feat(ee): attribute models, system catalog, value codec`.

---

### Task 5: API định nghĩa attribute (template workspace + attribute project)

**Files:**
- Create: `ee/work_item_types/serializers/attribute.py`, `views/{templates,attributes}.py`, `urls.py`
- Test: `tests/contract/app/ee/test_attribute_definitions.py`

**Interfaces:**
- Produces endpoints (§11): `GET|POST /api/workspaces/<slug>/attribute-templates/`, `PATCH|DELETE .../<id>/`, `POST .../<id>/options/`; `GET|POST /api/workspaces/<slug>/projects/<pid>/attributes/` (lọc `?issue_type_id=`), `PATCH|DELETE .../<id>/`, `POST .../reorder/` (`{ids: [uuid]}`), `POST .../apply-template/` (`{template_id, issue_type_id}`), options CRUD.
- Hành vi: attribute `is_system` không DELETE/đổi `name`/`field_type` (400 `system_attribute_locked`), chỉ PATCH `is_required` và (Project Phase) options; apply-template **sao chép** (`source_template` chỉ để tham khảo) → sửa template sau đó không đổi bản sao; đổi `field_type` khi đã có `AttributeValue` → 400 `type_change_blocked`; DELETE = soft delete.

- [ ] **Step 1: Tests** — quyền: member tạo attribute project → 403, project admin → 201; workspace admin mới tạo template; `test_apply_template_copies_independently` (sửa template → bản sao đổi nguyên); `test_system_attribute_locked`; `test_type_change_blocked_when_values_exist`; `test_soft_delete_keeps_values`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** DRF viewsets theo pattern `BaseViewSet` + `allow_permission` đang dùng ở `plane/app/views` (đọc 1 view mẫu trước khi viết). **Step 4: PASS; Commit** `feat(ee): attribute template and project attribute APIs`.

---

### Task 6: Giá trị attribute trong tạo/sửa work item + activity

**Files:**
- Modify (core seam): `app/serializers/issue.py` (`create`, `update`, `to_representation`), `app/views/issue/base.py` (`create`, `partial_update` — chỉ truyền thêm `attribute_values` vào context/serializer), `bgtasks/issue_activities_task.py` (nhánh `attribute.updated`, `parent.updated`)
- Create: `ee/work_item_types/views/values.py`
- Test: `tests/contract/app/ee/test_attribute_values.py`

**Interfaces:**
- Consumes: Task 3 `validate_work_item`, Task 4 `write_values`/`missing_required`.
- Produces: payload `attribute_values: {attribute_id: value}` nằm trong body POST/PATCH issue; `GET .../issues/<id>/attribute-values/` → `{attribute_id: value}`. `validate_work_item` được mở rộng: thiếu attribute bắt buộc (khi `triage=False`) → 400 `attribute_required` với `details.missing=[attribute_id,...]`.

- [ ] **Step 1: Tests** — `test_create_bug_missing_severity_400_lists_ids`; `test_create_story_with_values_persists_atomically` (lỗi một giá trị → không tạo issue); `test_patch_cannot_blank_required`; `test_guest_cannot_write_values`; `test_hidden_attribute_value_kept_not_returned`; `test_activity_recorded_for_value_and_parent_change`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** — trong `IssueCreateSerializer.create/update` bọc `Issue` + `write_values` cùng `transaction.atomic`; activity ghi qua `issue_activity.delay` như pattern hiện có. **Step 4: PASS; Commit** `feat(ee): attribute values on work item create/update`.

---

### Task 7: Quy tắc Scrum + cây con + các luồng sẵn có

**Files:**
- Create: `ee/work_item_types/{tree_ops,scrum_rules}.py`
- Modify (core seam, **mỗi điểm một dòng gọi hàm EE**): `app/views/issue/base.py` (`destroy`, `BulkDeleteIssuesEndpoint.delete`), `app/views/issue/archive.py` (`IssueArchiveViewSet`, `BulkArchiveIssuesEndpoint`), `bgtasks/issue_automation_task.py` (auto-archive/close), `app/views/cycle/issue.py` (`CycleIssueViewSet.create`), `app/views/intake/base.py` (`partial_update`, accept), `app/serializers/draft.py` + view chuyển draft→issue, luồng duplicate issue (xác minh bằng `grep -rn "duplicate" apps/api/plane/app/views/issue`), `app/views/issue/sub_issue.py`
- Test: `tests/contract/app/ee/test_scrum_rules.py`, `test_tree_ops.py`, `test_intake_triage.py`

**Interfaces:**
- Consumes: Task 3, 6.
- Produces:
  - `soft_delete_subtree(issue: Issue) -> int` (đồng bộ, một `deleted_at`, trả số issue xóa; không phụ thuộc celery), `restore_subtree(issue: Issue) -> int` (khôi phục hậu duệ cùng `deleted_at`), `archive_subtree(issue: Issue) -> int`, `subtree_count(issue: Issue) -> int` (cho hộp thoại xác nhận).
  - `assert_can_enter_cycle(issue: Issue, cycle: Cycle) -> list[str]` — raise `cycle_type_not_allowed` cho Epic/Feature; trả danh sách cảnh báo khi lệch cycle với Story cha.
  - `assert_can_complete(issue: Issue, new_state: State) -> None` — raise `open_children` với `details.children=[id,...]`.
  - `auto_archive_candidates(qs) -> QuerySet[Issue]` — chỉ issue mà mọi hậu duệ Completed/Cancelled.

- [ ] **Step 1: Tests** — `test_delete_story_soft_deletes_whole_subtree_same_deleted_at`; `test_restore_parent_restores_only_same_batch`; `test_bulk_delete_cascades`; `test_archive_story_archives_tasks_and_bugs`; `test_epic_cannot_join_cycle` (400 `cycle_type_not_allowed`), `test_task_cycle_mismatch_returns_warning_not_error`; `test_cannot_complete_story_with_open_task` (kanban PATCH state → 400 `open_children`), `test_complete_allowed_when_children_cancelled`; `test_reparent_reruns_validation`; intake: `test_intake_pending_bug_without_parent_or_severity_ok`, `test_intake_accept_without_parent_400`, `test_intake_reject_without_parent_ok`, `test_intake_accept_with_valid_parent_and_attributes_ok`; `test_duplicate_keeps_type_parent_values`; `test_draft_incomplete_ok_but_convert_validates`; `test_auto_archive_skips_open_trees`; `test_backlog_order_uses_sort_order_not_priority`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** — gọi `assert_can_complete` trong `IssueCreateSerializer.validate` khi `state` đổi; intake dùng `triage=True` khi `status in (-2, 0)` và `triage=False` khi chuyển `ACCEPTED` (1). **Step 4: Cập nhật allowlist; PASS; Commit** `feat(ee): scrum rules, subtree operations, intake triage mode`.

---

### Task 8: API public v1 + bulk-tree

**Files:**
- Create: `ee/work_item_types/{bulk_tree}.py`, `views/bulk_tree.py`, `plane/ee/api_urls.py`
- Modify (core seam): `apps/api/plane/api/serializers/issue.py` (`IssueSerializer` — nhận `type`, `parent`, `attribute_values`, gọi `validate_work_item`), `api/views/issue.py` (`IssueListCreateAPIEndpoint.post`, `IssueDetailAPIEndpoint.put/patch`)
- Test: `tests/contract/api/ee/test_v1_types.py`, `test_bulk_tree.py`

**Interfaces:**
- Produces: `POST /api/projects/<pid>/issues/bulk-tree/?dry_run=<bool>` và bản `/api/v1/workspaces/<slug>/projects/<pid>/issues/bulk-tree/` nhận `{"items": [{"ref": str, "type": TypeKey, "name": str, "parent_ref": str|None, "parent_id": UUID|None, "attribute_values": {...}, ...}]}`; `apply_bulk_tree(project: Project, items: list[dict], *, dry_run: bool, actor: User) -> BulkTreeResult` trả `{created: {ref: id}, errors: [{ref, code, message}]}`. Server sắp theo thứ tự gốc→lá, **một transaction**, lỗi một dòng → rollback tất cả; `dry_run` luôn rollback.

- [ ] **Step 1: Tests** — v1: tạo thiếu `type`/`parent` → 400; bulk: cây Epic→Feature→Story→Task tạo thành công 1 request; `test_bulk_rolls_back_on_one_bad_row`; `test_bulk_cycle_in_refs_rejected`; `test_bulk_unknown_parent_ref`; `test_dry_run_creates_nothing_but_reports_errors`; `test_bulk_missing_required_attribute_reports_row_ref`.
- [ ] **Step 2–4:** Run FAIL → implement (topological sort bằng Kahn, tạo qua cùng hàm tạo issue của core để giữ sequence_id/advisory lock) → PASS; Commit `feat(ee): public API types and bulk tree create`.

---

### Task 9: Import hai bước qua staging

**Files:**
- Create: `ee/work_item_types/models/import_batch.py` (+ migration `0002`), `importer.py`, `views/imports.py`
- Test: `tests/contract/app/ee/test_import_staging.py`

**Interfaces:**
- Produces: models `ImportBatch(project, status ∈ {draft, committed, failed}, created_by)`, `ImportRow(batch, ref, type, parent_ref, parent_id, name, data JSON, errors JSON)`. Endpoints dưới `projects/<pid>/imports/`: `POST /` (tạo batch), `POST <id>/rows/` (nạp dòng, B1), `PATCH <id>/rows/<row_id>/` (gán cha, B2), `POST <id>/validate/`, `POST <id>/commit/`. `validate_batch(batch) -> list[RowError]` tái dùng đúng `validate_work_item`; `commit_batch(batch) -> BulkTreeResult` gọi `apply_bulk_tree`.

- [ ] **Step 1: Tests** — `test_staging_rows_are_not_issues` (đếm `Issue` không đổi, backlog list không có); `test_validate_reports_missing_parent_and_wrong_parent_type_per_row`; `test_assign_parent_then_commit_creates_tree_atomically`; `test_commit_blocked_while_any_row_invalid`; `test_commit_twice_rejected`.
- [ ] **Step 2–4:** FAIL → implement → PASS; Commit `feat(ee): two-step import with staging`.

---

### Task 10: Hiển thị, lọc, group by theo type/attribute (backend)

**Files:**
- Modify (core seam — **xác minh trước**): schema/serializer của display properties (`ProjectUserPropertySerializer` trong `app/serializers/issue.py:364`, model `IssueUserProperty`), `plane/utils/filters/filter_backend.py` (`ComplexFilterBackend`), nơi xử lý `group_by` của `plane/utils/grouper.py` / `issue_queryset_grouper`
- Create: `ee/work_item_types/filters.py`
- Test: `tests/contract/app/ee/test_attribute_filters.py`

**Interfaces:**
- Produces: khóa `attribute:<uuid>` hợp lệ trong `display_properties`, `filters`, `group_by`; `build_attribute_q(attribute: Attribute, op: str, raw: Any) -> Q` (text `contains`; number/date `range`; boolean/select/multi_select/member `exact|in`); `group_by=type` và `group_by=attribute:<id>` chỉ cho `select|member|boolean`; filter `type`.

- [ ] **Step 1 (xác minh):** viết test `test_display_properties_accepts_attribute_key`; nếu core whitelist cứng khóa → ghi lại bằng test fail và mở rộng đúng điểm đó, ghi vào allowlist. **Step 2:** tests lọc từng kiểu + `test_group_by_text_attribute_400` + `test_filter_by_type`. **Step 3–4:** FAIL → implement, kiểm `EXPLAIN` dùng index (a smoke assertion `Index Scan` trên 10k dòng không bắt buộc, chỉ ghi chú) → PASS; Commit `feat(ee): filter and group by type and attributes`.

---

### Task 11: Frontend nền — types, service, store, đường dẫn EE

**Files:**
- Create: `apps/web/ee/work-item-types/{types.ts,constants.ts,services/attribute.service.ts,store/attribute.store.ts,hooks/use-attributes.ts}`
- Modify (core seam): `apps/web/store/root.store.ts` (đăng ký store), `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Produces: `TWorkItemTypeKey`, `TAttribute`, `TAttributeValue`, `PARENT_RULES_UI` (bản sao hằng số cho UI, **có test đồng bộ ở Task 15**); `AttributeService` (CRUD template/attribute/options/apply-template/reorder/values/bulk-tree/import); `AttributeStore` (MobX) với `getAttributesByType(projectId, typeKey)`, `fetchProjectAttributes(workspaceSlug, projectId)`, `allowedParentTypes(typeKey): TWorkItemTypeKey[]`.

- [ ] **Step 1:** viết types + service + store theo pattern store hiện có (`apps/web/store/issue/*`, service pattern `apps/web/services/*`). **Step 2:** `pnpm turbo run check:types --filter=web` → PASS. **Step 3:** `pnpm check:lint` → PASS. **Step 4: Commit** `feat(web): work item types foundation`.

---

### Task 12: Frontend cấu hình attribute (workspace library + project settings)

**Files:**
- Create: `apps/web/ee/work-item-types/pages/{workspace-attribute-library,project-attributes}.tsx`, `components/attribute-form/*` (một editor mỗi `field_type`), `components/apply-template-modal.tsx`
- Modify (core seam, route + menu mỏng): `apps/web/app/(all)/[workspaceSlug]/(settings)/settings/projects/[projectId]/attributes/page.tsx` (mới), mục menu trong project settings và workspace settings

**Interfaces:**
- Consumes: Task 11 store/service.
- Produces: UI chọn type → danh sách attribute (kéo thả sắp xếp), tạo/sửa/ẩn/xóa (attribute system chỉ cho bật/tắt bắt buộc), áp dụng template (modal chọn template + type), quản lý option cho select.

- [ ] **Step 1:** dựng trang + route. **Step 2:** `check:types` + `check:lint` PASS. **Step 3: Kiểm trên browser thật** (xem Task 15 quy trình) cho: tạo attribute select, áp dụng template rồi sửa template không đổi bản sao, attribute system không xóa được. **Step 4: Commit** `feat(web): attribute settings pages`.

---

### Task 13: Frontend form tạo/sửa, chi tiết, cây cha–con

**Files:**
- Create: `apps/web/ee/work-item-types/components/{type-selector,parent-picker,attribute-fields,type-badge,hierarchy-breadcrumb,children-tree}.tsx`
- Modify (core seam): `components/issues/issue-modal/form.tsx` và `issue-modal/context/issue-modal-context.tsx` (nối vào hook sẵn có `handlePropertyValuesValidation`, `handleCreateUpdatePropertyValues`, `issuePropertyValues`, `handleCreateSubWorkItem`), `components/issues/issue-detail/sidebar.tsx` (slot attribute), `issue-detail/main-content.tsx` (breadcrumb cha, cây con), `issue-layouts/list/block.tsx` + kanban/spreadsheet card (badge type), form quick-add (list/kanban/spreadsheet) + tạo từ cycle/module

**Interfaces:**
- Consumes: Task 11.
- Produces: chọn type trước → hiện attribute (core + cố định + custom) → `ParentPicker` chỉ liệt kê issue có type ∈ `allowedParentTypes(type)` cùng project; sub-issue điền sẵn cha và chỉ cho chọn type con hợp lệ; lỗi 400 của backend (`attribute_required`, `parent_required`, `open_children`, `cycle_type_not_allowed`) hiện đúng field; validate phía client trước khi gửi; cảnh báo lệch cycle hiện dạng toast; xóa/lưu trữ issue có con mở hộp thoại nêu `subtree_count`.

- [ ] **Step 1:** nối form theo hook sẵn có; quick-add inline có type+cha. **Step 2:** `check:types` + `check:lint` PASS. **Step 3: Browser:** tạo cây Epic→Feature→Story→Task→Sub-task; thử tạo Task không cha (bị chặn ở UI); Bug thiếu Severity (lỗi trên field); kéo Story sang Done khi còn Task mở (lỗi liệt kê con). **Step 4: Commit** `feat(web): type-aware work item form, detail and tree`.

---

### Task 14: Frontend hiển thị/lọc/group by, import, intake

**Files:**
- Create: `apps/web/ee/work-item-types/components/{attribute-columns,attribute-filter,import-wizard,intake-accept-fields}.tsx`
- Modify (core seam): display properties dropdown, rich-filter config (`packages/types/src/rich-filters`, `apps/web/components/rich-filters`), group-by options, intake accept UI (`apps/web/components/inbox`), màn import mới

**Interfaces:**
- Consumes: Task 10 backend, Task 9 endpoints.
- Produces: bật/tắt cột attribute (cố định + custom) như display property; filter theo từng kiểu; group by type và attribute select/member/boolean; wizard import: B1 nạp CSV → B2 bảng gán cha/sửa lỗi → dry-run → Commit; form intake cho Bug/User Story, màn chấp nhận bắt buộc chọn cha + điền attribute thiếu.

- [ ] **Step 1:** dựng các component. **Step 2:** `check:types` + `check:lint` PASS. **Step 3: Browser:** bật cột Story Points, lọc Bug theo Severity, group by type; import CSV có dòng thiếu cha → sửa → commit; intake Bug không cha → accept chọn cha. **Step 4: Commit** `feat(web): attribute columns, filters, import wizard, intake accept`.

---

### Task 15: i18n, đồng bộ hằng số, nghiệm thu browser

**Files:**
- Modify: `packages/i18n/src/locales/*` (qua skill `translate`: en + vi tối thiểu, plural/placeholder đúng quy tắc), `apps/api/plane/tests/unit/ee/test_ui_rules_sync.py`
- Create: `docs/superpowers/plans/acceptance-checklist.md` (checklist nghiệm thu)

**Interfaces:**
- Consumes: mọi task trước.

- [ ] **Step 1:** `test_ui_rules_sync`: đọc `PARENT_RULES_UI` trong `apps/web/ee/work-item-types/constants.ts` bằng regex/JSON và khẳng định bằng `PARENT_RULES` backend. **Step 2:** thêm toàn bộ chuỗi i18n; chạy skill `translate` để rà. **Step 3:** `docker compose -f docker-compose-local.yml up` (chỉ file cho phép), chạy `seed_work_item_types`, đi hết checklist: 6 type, luật cha–con ở UI+API, attribute 2 cấp, bắt buộc, cycle/completion rule, xóa cây, intake, bulk-tree, import, cột/lọc/group. **Step 4:** `pnpm check`, `bash scripts/check-core-allowlist.sh preview`, full `docker-compose-test.yml` suite → tất cả xanh. **Step 5: Commit** `chore(ee): i18n, rules sync, acceptance checklist`.

---

## Self-Review

**Spec coverage:** §3 → T2,3; §4 → T4; §5 → T4,5; §6 → T6,7,13; §7 (API/bulk/import/intake/draft/duplicate/cycle/xóa) → T7,8,9; §8 → T10,14; §9 → T4,9; §10 (khung EE + seam) → T1 và allowlist cập nhật ở T3,6,7,8,10–14; §11 → T5,8,9; §12 quyền → T5,6 test; §14 kiểm thử → từng task + T15. Không có mục nào thiếu task.

**Rủi ro lớn nhất (hội đồng đề xuất xử lý sớm):** (a) T10 phải xác minh whitelist display-properties/filter **ngay đầu** — nếu core cứng, chi phí tăng; chạy bước xác minh của T10 song song với T2 nếu cần. (b) T7 chạm nhiều nhất file core; mỗi điểm chỉ một dòng gọi hàm EE.

**Nhất quán tên:** `validate_work_item`, `WorkItemValidationError`, `TypeKey`, `PARENT_RULES`, `soft_delete_subtree`, `apply_bulk_tree`, `write_values`, `missing_required` dùng đồng nhất xuyên task.
