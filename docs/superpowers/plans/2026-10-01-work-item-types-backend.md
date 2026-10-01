# Work Item Types — Backend Implementation Plan (Plan 1/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend của work item types Scrum/Agile: preset theo process, CRUD type, gán type theo project, ràng buộc phân cấp cha-con, mặc định type, an toàn IDOR.

**Architecture:** Toàn bộ logic mới nằm trong app plugin `plane.ee` (`apps/api/plane/ee/work_item_types/`). Validation chạy qua hook `pre_save` của `Issue` đăng ký trong `EeConfig.ready()` (không sửa core cho việc này). Core chỉ có các seam nhỏ: field `type_id` ở serializer, validate tường minh ở `bulk_update` sub-issue, `type_id` ở đường đọc.

**Tech Stack:** Django 5.2, DRF, pytest (`--ds=plane.settings.ee_test`), model sẵn có `IssueType`/`ProjectIssueType`/`Issue.type`.

**Spec:** `docs/superpowers/specs/2026-10-01-work-item-types-design.md`. Plan 2 (frontend) viết sau khi plan này xong.

## Global Constraints
- Không migration core. Không sửa `IssueManager`. Không route `/epics/`. API **không trả `is_epic`** cho issue (chỉ `type_id`).
- Quy tắc phân cấp: `child.level < parent.level`; Epic (`is_epic`) không có cha; `level == 0` bắt buộc có cha và cha `level ∈ {1, 2}`; cấm chu trình; chỉ validate khi `type`/`parent` thay đổi.
- Level preset: Epic 4, Feature 3, Bug 2, PBI 2 (Scrum), User Story 2 (Agile), Task 1, Sub-task 0. Mặc định: PBI (Scrum) / User Story (Agile). Impediment/Issue không có trong preset.
- Preset lưu `external_source="plane-work-item-types"`, `external_id=<key>`. Preset không xoá được, không đổi `level`.
- Quyền: CRUD type = workspace **Admin** (role 20, dùng `WorkspaceOwnerPermission`; `WorkSpaceAdminPermission` cho cả Member nên KHÔNG dùng). Gán type/process ở project = project Admin (`ProjectAdminPermission`). Đọc = thành viên project/workspace.
- Lỗi IDOR dùng thông báo chung ("Invalid work item type", "Invalid parent"). Mọi truy vấn lọc theo `slug`/`project_id` từ URL.
- Giới hạn ≤ 50 type/workspace; tên unique không phân biệt hoa thường (validate trong app).
- `logo_props.icon.name` khớp `^[A-Za-z0-9]{1,64}$` (whitelist đầy đủ nằm ở icon picker frontend); màu `^#[0-9a-fA-F]{6}$`; chỉ khoá `in_use`, `icon{name,color,background_color}`, `emoji{value,url}`.
- File mới mang header bản quyền AGPL như các file `plane/ee/*`. Test đặt trong `apps/api/plane/tests/unit/ee/work_item_types/`, đánh dấu `@pytest.mark.unit` hoặc `contract`.
- Chạy test: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/work_item_types` (từ thư mục gốc repo). Các lệnh `pytest ...` trong plan là rút gọn của lệnh này.

## File Structure
| File | Trách nhiệm |
|---|---|
| `plane/ee/work_item_types/__init__.py` | package rỗng |
| `.../rules.py` | hàm thuần: `TypeInfo`, `hierarchy_error`, `creates_cycle` |
| `.../presets.py` | định nghĩa preset + `PROCESSES` |
| `.../seed.py` | `seed_types(workspace)`, `apply_process(project, process)`, `project_process(project)` |
| `.../validation.py` | `validate_issue_write(issue)` (DB), `resolve_default_type(project_id)` |
| `.../signals.py` | `pre_save` receiver gọi `validate_issue_write` |
| `.../serializers.py` | `IssueTypeSerializer`, `validate_logo_props` |
| `.../views.py` | endpoint workspace + project |
| `.../urls.py` | route |
| `plane/ee/apps.py`, `plane/ee/urls.py` | đăng ký signal, mount route |
| `plane/tests/unit/ee/work_item_types/` | `conftest.py` + test từng module |

---

### Task 1: Quy tắc phân cấp thuần (rules.py)

**Files:**
- Create: `apps/api/plane/ee/work_item_types/__init__.py`, `apps/api/plane/ee/work_item_types/rules.py`
- Create: `apps/api/plane/tests/unit/ee/work_item_types/__init__.py`, `apps/api/plane/tests/unit/ee/work_item_types/test_rules.py`

**Interfaces:**
- Produces: `TypeInfo(id: str, level: int, is_epic: bool = False)`; `hierarchy_error(child: TypeInfo, parent: TypeInfo | None) -> str | None`; `creates_cycle(issue_id, parent_id, parent_of: Callable[[Any], Any]) -> bool`.

- [ ] **Step 1: Viết test fail** — `test_rules.py`:

```python
import pytest

from plane.ee.work_item_types.rules import TypeInfo, creates_cycle, hierarchy_error

EPIC = TypeInfo("epic", 4, is_epic=True)
FEATURE = TypeInfo("feature", 3)
STORY = TypeInfo("story", 2)
BUG = TypeInfo("bug", 2)
TASK = TypeInfo("task", 1)
SUB = TypeInfo("sub", 0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "child,parent",
    [(FEATURE, EPIC), (STORY, FEATURE), (STORY, EPIC), (TASK, STORY), (TASK, BUG), (SUB, TASK), (SUB, STORY), (EPIC, None), (STORY, None), (TASK, None)],
)
def test_allowed(child, parent):
    assert hierarchy_error(child, parent) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "child,parent",
    [(EPIC, FEATURE), (STORY, STORY), (STORY, TASK), (TASK, TASK), (SUB, EPIC), (SUB, FEATURE), (SUB, SUB), (SUB, None)],
)
def test_rejected(child, parent):
    assert hierarchy_error(child, parent)


@pytest.mark.unit
def test_creates_cycle():
    parents = {"a": "b", "b": "c", "c": None}
    assert creates_cycle("c", "a", parents.get)  # c -> a would loop a->b->c->a
    assert not creates_cycle("a", "c", parents.get)
    assert creates_cycle("a", "a", parents.get)
    assert not creates_cycle("a", None, parents.get)


@pytest.mark.unit
def test_creates_cycle_stops_on_existing_loop():
    parents = {"x": "y", "y": "x"}  # corrupt legacy data must not hang
    assert not creates_cycle("z", "x", parents.get)
```

- [ ] **Step 2: Chạy, xác nhận fail** — `pytest plane/tests/unit/ee/work_item_types/test_rules.py -v` → FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Cài đặt** — `__init__.py` chỉ chứa header bản quyền. `rules.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from dataclasses import dataclass

# Sub-tasks (level 0) may only sit under level-1/2 items (Task/Bug/Story/PBI), never under Epic/Feature.
SUBTASK_PARENT_LEVELS = frozenset({1, 2})


@dataclass(frozen=True)
class TypeInfo:
    id: str
    level: int
    is_epic: bool = False


def hierarchy_error(child: TypeInfo, parent: TypeInfo | None) -> str | None:
    """Return a message when (child type, parent type) is not allowed, else None."""
    if parent is None:
        return "A sub-task needs a parent" if child.level == 0 else None
    if child.is_epic:
        return "An epic cannot have a parent"
    if child.level >= parent.level:
        return "The parent must be a higher level than its child"
    if child.level == 0 and parent.level not in SUBTASK_PARENT_LEVELS:
        return "A sub-task can only sit under a task, bug or story level item"
    return None


def creates_cycle(issue_id, parent_id, parent_of) -> bool:
    """True if making `parent_id` the parent of `issue_id` closes a loop. `parent_of(id)` -> parent id | None."""
    seen = set()
    current = parent_id
    while current is not None and current not in seen:
        if current == issue_id:
            return True
        seen.add(current)
        current = parent_of(current)
    return False
```

- [ ] **Step 4: Chạy test** → PASS.
- [ ] **Step 5: Commit** — `git add apps/api/plane/ee/work_item_types apps/api/plane/tests/unit/ee/work_item_types && git commit -m "feat(ee): work item type hierarchy rules"`

---

### Task 2: Preset + seed + process của project

**Files:**
- Create: `plane/ee/work_item_types/presets.py`, `plane/ee/work_item_types/seed.py`
- Create: `plane/tests/unit/ee/work_item_types/conftest.py`, `test_seed.py`

**Interfaces:**
- Consumes: `IssueType`, `ProjectIssueType`, `Project`.
- Produces: `PROCESSES = ("scrum", "agile")`; `SOURCE = "plane-work-item-types"`; `seed_types(workspace) -> dict[str, IssueType]` (key → type, idempotent); `apply_process(project, process) -> None` (gán bộ type, đặt default; đổi process thì bỏ gán type riêng của process cũ nếu **không có issue dùng**, ngược lại raise `ProcessChangeBlocked`); `project_process(project) -> str | None`; `class ProcessChangeBlocked(Exception)`.

- [ ] **Step 1: conftest + test fail.** `conftest.py`:

```python
import pytest

from plane.db.models import Project, ProjectMember


@pytest.fixture
def project(db, workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=p, member=create_user, workspace=workspace, role=20)
    return p
```

`test_seed.py`:

```python
import pytest

from plane.db.models import Issue, IssueType, ProjectIssueType, State
from plane.ee.work_item_types.seed import ProcessChangeBlocked, apply_process, project_process, seed_types


def names(project):
    return {pit.issue_type.name for pit in ProjectIssueType.objects.filter(project=project)}


@pytest.mark.unit
def test_seed_is_idempotent(workspace):
    first = seed_types(workspace)
    second = seed_types(workspace)
    assert {k: v.id for k, v in first.items()} == {k: v.id for k, v in second.items()}
    assert IssueType.objects.filter(workspace=workspace).count() == len(first)
    assert first["epic"].is_epic and first["epic"].level == 4
    assert first["sub_task"].level == 0


@pytest.mark.unit
def test_apply_scrum_and_agile(workspace, project):
    apply_process(project, "scrum")
    assert names(project) == {"Epic", "Feature", "Bug", "Task", "Sub-task", "Product Backlog Item"}
    assert project_process(project) == "scrum"
    default = ProjectIssueType.objects.get(project=project, is_default=True)
    assert default.issue_type.name == "Product Backlog Item"
    project.refresh_from_db()
    assert project.is_issue_type_enabled is True

    apply_process(project, "agile")  # no issue uses PBI -> switch allowed
    assert "Product Backlog Item" not in names(project) and "User Story" in names(project)
    assert project_process(project) == "agile"


@pytest.mark.unit
def test_switch_blocked_when_exclusive_type_in_use(workspace, project, create_user):
    apply_process(project, "scrum")
    pbi = IssueType.objects.get(workspace=workspace, external_id="product_backlog_item")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="I", workspace=workspace, project=project, state=state, type=pbi, created_by=create_user)
    with pytest.raises(ProcessChangeBlocked):
        apply_process(project, "agile")


@pytest.mark.unit
def test_project_process_none_when_unset(project):
    assert project_process(project) is None
```

- [ ] **Step 2: Chạy** → FAIL (module không tồn tại).
- [ ] **Step 3: Cài đặt.** `presets.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

SOURCE = "plane-work-item-types"
PROCESSES = ("scrum", "agile")

# key: (name, level, is_epic, icon, color)
PRESETS = {
    "epic": ("Epic", 4, True, "Zap", "#8B5CF6"),
    "feature": ("Feature", 3, False, "Layers", "#EC4899"),
    "bug": ("Bug", 2, False, "Bug", "#EF4444"),
    "task": ("Task", 1, False, "CheckSquare", "#3B82F6"),
    "sub_task": ("Sub-task", 0, False, "ListTree", "#64748B"),
    "product_backlog_item": ("Product Backlog Item", 2, False, "BookOpen", "#10B981"),
    "user_story": ("User Story", 2, False, "BookOpen", "#10B981"),
}
SHARED = ("epic", "feature", "bug", "task", "sub_task")
EXCLUSIVE = {"scrum": "product_backlog_item", "agile": "user_story"}  # also the project default
```

`seed.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import transaction

from plane.db.models import Issue, IssueType, Project, ProjectIssueType
from plane.ee.work_item_types.presets import EXCLUSIVE, PRESETS, PROCESSES, SHARED, SOURCE


class ProcessChangeBlocked(Exception):
    pass


def seed_types(workspace) -> dict:
    """Create the preset types of a workspace once (idempotent). Returns key -> IssueType."""
    result = {}
    with transaction.atomic():
        for key, (name, level, is_epic, icon, color) in PRESETS.items():
            obj, _ = IssueType.objects.get_or_create(
                workspace=workspace,
                external_source=SOURCE,
                external_id=key,
                defaults={
                    "name": name,
                    "level": level,
                    "is_epic": is_epic,
                    "logo_props": {
                        "in_use": "icon",
                        "icon": {"name": icon, "color": "#FFFFFF", "background_color": color},
                    },
                },
            )
            result[key] = obj
    return result


def project_process(project) -> str | None:
    keys = set(
        ProjectIssueType.objects.filter(project=project, issue_type__external_source=SOURCE).values_list(
            "issue_type__external_id", flat=True
        )
    )
    for process, exclusive in EXCLUSIVE.items():
        if exclusive in keys:
            return process
    return None


@transaction.atomic
def apply_process(project, process: str) -> None:
    if process not in PROCESSES:
        raise ValueError(process)
    types = seed_types(project.workspace)
    current = project_process(project)
    if current and current != process:
        old = types[EXCLUSIVE[current]]
        if Issue.objects.filter(project=project, type=old).exists():
            raise ProcessChangeBlocked(f"{old.name} is still used by work items in this project")
        ProjectIssueType.objects.filter(project=project, issue_type=old).delete()
    wanted = [*SHARED, EXCLUSIVE[process]]
    ProjectIssueType.objects.filter(project=project, is_default=True).update(is_default=False)
    for key in wanted:
        pit, _ = ProjectIssueType.objects.get_or_create(
            project=project, issue_type=types[key], defaults={"level": types[key].level}
        )
        pit.is_default = key == EXCLUSIVE[process]
        pit.save(update_fields=["is_default"])
    Project.objects.filter(pk=project.pk).update(is_issue_type_enabled=True)
```

> Lưu ý: `ProjectIssueType.save` gán `workspace` từ `project`; `get_or_create` ở trên truyền `project` nên đủ. `ProjectIssueType.objects.get_or_create` dùng manager mặc định (đã lọc `deleted_at`); nếu repo dùng `SoftDeletionManager`, hàng đã xoá mềm không bị tái dùng — chấp nhận.

- [ ] **Step 4: Chạy** `pytest plane/tests/unit/ee/work_item_types/test_seed.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(ee): work item type presets, seed and per-project process`.

---

### Task 3: Validation DB + hook pre_save

**Files:**
- Create: `plane/ee/work_item_types/validation.py`, `plane/ee/work_item_types/signals.py`
- Modify: `apps/api/plane/ee/apps.py` (đăng ký signal trong `ready()`)
- Test: `plane/tests/unit/ee/work_item_types/test_validation.py`

**Interfaces:**
- Consumes: `hierarchy_error`, `creates_cycle`, `TypeInfo` (Task 1); `apply_process` (Task 2, chỉ trong test).
- Produces: `validate_issue_write(issue) -> None` (raise `rest_framework.exceptions.ValidationError`; không làm gì khi project chưa bật `is_issue_type_enabled`; điền `issue.type_id` mặc định khi tạo mà thiếu type); `resolve_default_type_id(project_id)`; receiver `issue_pre_save`.

Hành vi của `validate_issue_write(issue)`:
1. Nếu `Project.is_issue_type_enabled` là False → return.
2. Lấy giá trị cũ: nếu `issue._state.adding` thì `old=(None, None)` (và coi là "đổi"), ngược lại `Issue.objects.filter(pk).values_list("type_id","parent_id").first()`.
3. Khi tạo và `type_id is None` → gán type mặc định của project (`ProjectIssueType.is_default`).
4. Nếu `(type_id, parent_id) == old` và không phải tạo → return (không validate khi không đổi).
5. Nếu `type_id` đổi: type phải có trong `ProjectIssueType` của project (`deleted_at` null) và `is_active`; nếu không → `ValidationError({"type_id": "Invalid work item type"})`.
6. Resolve `TypeInfo` của issue (type null → type mặc định của project) và của parent (`Issue.objects.filter(pk=parent_id, project_id=issue.project_id)`; không có → `ValidationError({"parent_id": "Invalid parent"})`; parent type null → mặc định).
7. `hierarchy_error(child, parent)` → `ValidationError({"parent_id": msg})`.
8. Nếu `parent_id` đổi và có parent: `creates_cycle(issue.id, parent_id, parent_of)`; `parent_of(i)=Issue.objects.filter(pk=i).values_list("parent_id", flat=True).first()` → `ValidationError({"parent_id": "Parent would create a loop"})`.
9. Nếu issue đã có (không phải tạo) và `type_id` đổi: kiểm tra từng con trực tiếp: `hierarchy_error(child_info, new_self_info)`; có con mà type mới `level == 0` → lỗi "A work item with sub-items cannot become a sub-task"; Epic đổi sang non-Epic khi còn con → lỗi. Tối đa liệt kê 5 con xung đột trong message.

- [ ] **Step 1: Viết test fail** — `test_validation.py` (dùng `apply_process(project, "scrum")`; helper tạo issue với `Issue.objects.create(...)`):

```python
import pytest
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueType, State
from plane.ee.work_item_types.seed import apply_process


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    t = {x.external_id: x for x in IssueType.objects.filter(workspace=workspace)}

    def make(name, key=None, parent=None):
        return Issue.objects.create(
            name=name, workspace=workspace, project=project, state=state, parent=parent,
            type=t[key] if key else None, created_by=create_user,
        )

    return make, t, project


@pytest.mark.unit
def test_default_type_filled_on_create(env):
    make, t, _ = env
    assert make("a").type_id == t["product_backlog_item"].id


@pytest.mark.unit
def test_task_under_pbi_ok_subtask_under_epic_rejected(env):
    make, t, _ = env
    pbi = make("pbi", "product_backlog_item")
    make("task", "task", parent=pbi)
    epic = make("epic", "epic")
    with pytest.raises(ValidationError):
        make("sub", "sub_task", parent=epic)


@pytest.mark.unit
def test_epic_with_parent_and_subtask_without_parent_rejected(env):
    make, t, _ = env
    feature = make("f", "feature")
    with pytest.raises(ValidationError):
        make("e", "epic", parent=feature)
    with pytest.raises(ValidationError):
        make("s", "sub_task")


@pytest.mark.unit
def test_unchanged_type_and_parent_not_revalidated(env):
    make, t, _ = env
    pbi = make("pbi", "product_backlog_item")
    task = make("task", "task", parent=pbi)
    IssueType.objects.filter(pk=t["task"].pk).update(level=5)  # legacy data now violates the rule
    task.name = "renamed"
    task.save()  # must not raise


@pytest.mark.unit
def test_cycle_rejected(env):
    make, t, _ = env
    a = make("a", "feature")
    b = make("b", "product_backlog_item", parent=a)
    a.parent = b
    with pytest.raises(ValidationError):
        a.save()


@pytest.mark.unit
def test_change_type_blocked_by_children(env):
    make, t, _ = env
    pbi = make("pbi", "product_backlog_item")
    make("task", "task", parent=pbi)
    pbi.type = t["task"]  # level 1 can't hold a level-1 child
    with pytest.raises(ValidationError):
        pbi.save()
    pbi.refresh_from_db()
    pbi.type = t["sub_task"]
    with pytest.raises(ValidationError):
        pbi.save()


@pytest.mark.unit
def test_type_from_other_workspace_rejected_with_generic_message(env, create_user):
    from plane.db.models import Workspace

    make, t, project = env
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="X", level=2)
    with pytest.raises(ValidationError) as exc:
        make_issue = make("z")
        make_issue.type = foreign
        make_issue.save()
    assert "Invalid work item type" in str(exc.value.detail)


@pytest.mark.unit
def test_disabled_project_is_untouched(db, workspace, project, create_user):
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    issue = Issue.objects.create(name="x", workspace=workspace, project=project, state=state, created_by=create_user)
    assert issue.type_id is None
```

- [ ] **Step 2: Chạy** → FAIL (chưa có validation/signal; nhiều test fail vì không raise).
- [ ] **Step 3: Cài đặt `validation.py`:**

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueType, Project, ProjectIssueType
from plane.ee.work_item_types.rules import TypeInfo, creates_cycle, hierarchy_error


def _info(issue_type) -> TypeInfo:
    return TypeInfo(str(issue_type.id), int(issue_type.level), issue_type.is_epic)


def resolve_default_type_id(project_id):
    return (
        ProjectIssueType.objects.filter(project_id=project_id, is_default=True)
        .values_list("issue_type_id", flat=True)
        .first()
    )


def _type_info(type_id, project_id) -> TypeInfo | None:
    type_id = type_id or resolve_default_type_id(project_id)
    obj = IssueType.objects.filter(pk=type_id).first() if type_id else None
    return _info(obj) if obj else None


def validate_issue_write(issue) -> None:
    # ponytail: one extra query per Issue save to read the project flag; cache per project if it shows up in profiles
    if not Project.objects.filter(pk=issue.project_id, is_issue_type_enabled=True).exists():
        return
    adding = issue._state.adding
    old = (None, None) if adding else Issue.objects.filter(pk=issue.pk).values_list("type_id", "parent_id").first()
    if adding and issue.type_id is None:
        issue.type_id = resolve_default_type_id(issue.project_id)
    new = (issue.type_id, issue.parent_id)
    if not adding and new == old:
        return
    type_changed = adding or issue.type_id != (old or (None, None))[0]
    parent_changed = adding or issue.parent_id != (old or (None, None))[1]

    if type_changed and issue.type_id is not None:
        allowed = ProjectIssueType.objects.filter(
            project_id=issue.project_id, issue_type_id=issue.type_id, issue_type__is_active=True
        ).exists()
        if not allowed:
            raise ValidationError({"type_id": "Invalid work item type"})

    child = _type_info(issue.type_id, issue.project_id)
    if child is None:
        return
    parent = None
    if issue.parent_id:
        parent_row = Issue.objects.filter(pk=issue.parent_id, project_id=issue.project_id).first()
        if parent_row is None:
            raise ValidationError({"parent_id": "Invalid parent"})
        parent = _type_info(parent_row.type_id, issue.project_id)
    if type_changed or parent_changed:
        message = hierarchy_error(child, parent)
        if message:
            raise ValidationError({"parent_id": message})
    if parent_changed and issue.parent_id and not adding:
        parent_of = lambda i: Issue.objects.filter(pk=i).values_list("parent_id", flat=True).first()  # noqa: E731
        if creates_cycle(issue.pk, issue.parent_id, parent_of):
            raise ValidationError({"parent_id": "Parent would create a loop"})
    if type_changed and not adding:
        conflicts = []
        for sub in Issue.objects.filter(parent_id=issue.pk).only("id", "name", "type_id")[:200]:
            sub_info = _type_info(sub.type_id, issue.project_id)
            if sub_info and hierarchy_error(sub_info, child):
                conflicts.append(sub.name)
        if conflicts:
            raise ValidationError({"type_id": f"Conflicts with sub-items: {', '.join(conflicts[:5])}"})
```

`signals.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db.models.signals import pre_save
from django.dispatch import receiver

from plane.db.models import Issue
from plane.ee.work_item_types.validation import validate_issue_write


@receiver(pre_save, sender=Issue, dispatch_uid="ee_work_item_type_validate")
def issue_pre_save(sender, instance, raw=False, **kwargs):
    if not raw:
        validate_issue_write(instance)
```

`apps.py` — trong `ready()` thêm: `from plane.ee.work_item_types import signals  # noqa: F401`.

- [ ] **Step 4: Chạy** `pytest plane/tests/unit/ee/work_item_types -v` → PASS (cả test_rules/test_seed). Nếu `test_change_type_blocked_by_children` fail do lỗi dùng `[:200]` với `.only`, bỏ `.only(...)`.
- [ ] **Step 5: Chạy hồi quy core** `pytest plane/tests/unit plane/tests/contract -q --ds=plane.settings.ee_test` → không test core nào hỏng (dự án chưa bật tính năng nên hook trả sớm). Nếu hỏng, dừng và báo.
- [ ] **Step 6: Commit** — `feat(ee): validate work item type and parent on Issue save`.

---

### Task 4: Serializer + view CRUD type (workspace)

**Files:**
- Create: `plane/ee/work_item_types/serializers.py`, `plane/ee/work_item_types/views.py`, `plane/ee/work_item_types/urls.py`
- Modify: `plane/ee/urls.py`
- Test: `plane/tests/unit/ee/work_item_types/test_workspace_api.py`

**Interfaces:**
- Consumes: `seed_types` (Task 2).
- Produces: `GET/POST /api/workspaces/<slug>/work-item-types/`, `GET/PATCH/DELETE /api/workspaces/<slug>/work-item-types/<uuid:pk>/`; `validate_logo_props(value) -> dict`.
  - `POST` body `{name, description?, level, is_epic?, logo_props?}`. Chặn: tên trùng (không phân biệt hoa thường), >50 type, `level` không thuộc 0..9.
  - `PATCH`: không đổi `level`/`is_epic` nếu type đã có issue (409) hoặc là preset; được đổi `name`, `description`, `logo_props`, `is_active`.
  - `DELETE ?migrate_to=<uuid>`: preset hoặc `is_default` → 409; có issue dùng (`Issue.objects`, gồm archived/draft; soft-deleted không còn trong manager mặc định nên không cần tính) mà không có `migrate_to` → 409 `{"error": "...", "count": n}`; có `migrate_to` (cùng workspace, khác id, active) → `Issue.objects.filter(type=obj).update(type=target)` trong `transaction.atomic`, rồi soft-delete type + `ProjectIssueType`.
  - Quyền: đọc = `WorkspaceViewerPermission`; ghi = `WorkspaceOwnerPermission` (xem Global Constraints).

- [ ] **Step 1: Viết test fail** — `test_workspace_api.py`:

```python
import pytest
from rest_framework import status

from plane.db.models import Issue, IssueType, State, User, Workspace, WorkspaceMember
from plane.ee.work_item_types.seed import seed_types


def base(ws):
    return f"/api/workspaces/{ws.slug}/work-item-types/"


@pytest.fixture
def seeded(workspace):
    return seed_types(workspace)


@pytest.mark.contract
def test_list(session_client, workspace, seeded):
    r = session_client.get(base(workspace))
    assert r.status_code == 200
    assert {x["name"] for x in r.json()} >= {"Epic", "Feature", "Task"}


@pytest.mark.contract
def test_create_custom_type(session_client, workspace, seeded):
    body = {"name": "Spike", "level": 1, "logo_props": {"in_use": "icon", "icon": {"name": "Zap", "color": "#fff000", "background_color": "#123456"}}}
    r = session_client.post(base(workspace), body, format="json")
    assert r.status_code == 201, r.content
    assert IssueType.objects.filter(workspace=workspace, name="Spike").exists()


@pytest.mark.contract
@pytest.mark.parametrize(
    "logo",
    [
        {"in_use": "icon", "icon": {"name": "<script>", "color": "#fff000"}},
        {"in_use": "icon", "icon": {"name": "Zap", "color": "red"}},
        {"in_use": "icon", "evil": 1},
    ],
)
def test_bad_logo_props_rejected(session_client, workspace, seeded, logo):
    r = session_client.post(base(workspace), {"name": "X", "level": 1, "logo_props": logo}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_duplicate_name_case_insensitive(session_client, workspace, seeded):
    r = session_client.post(base(workspace), {"name": "task", "level": 1}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_member_cannot_write_but_can_read(api_client, workspace, seeded):
    member = User.objects.create(email="m@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    api_client.force_authenticate(user=member)
    assert api_client.get(base(workspace)).status_code == 200
    assert api_client.post(base(workspace), {"name": "Z", "level": 1}, format="json").status_code == 403


@pytest.mark.contract
def test_cannot_touch_other_workspace(session_client, workspace, seeded, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=1)
    assert session_client.patch(f"{base(workspace)}{foreign.id}/", {"name": "hack"}, format="json").status_code == 404


@pytest.mark.contract
def test_preset_level_is_locked_and_not_deletable(session_client, workspace, seeded):
    url = f"{base(workspace)}{seeded['task'].id}/"
    assert session_client.patch(url, {"level": 3}, format="json").status_code == 409
    assert session_client.delete(url).status_code == 409


@pytest.mark.contract
def test_delete_in_use_requires_migrate_to(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    issue = Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=custom, created_by=create_user)
    url = f"{base(workspace)}{custom.id}/"
    r = session_client.delete(url)
    assert r.status_code == 409 and r.json()["count"] == 1
    r = session_client.delete(f"{url}?migrate_to={seeded['task'].id}")
    assert r.status_code == 204
    issue.refresh_from_db()
    assert issue.type_id == seeded["task"].id
    assert not IssueType.objects.filter(pk=custom.pk).exists()


@pytest.mark.contract
def test_type_cap(session_client, workspace, seeded, settings):
    settings.WORK_ITEM_TYPES_MAX = 7  # presets already fill 7
    assert session_client.post(base(workspace), {"name": "One more", "level": 1}, format="json").status_code == 400
```

> `project` fixture đến từ `conftest.py` của Task 2. `IssueType.objects` là manager mặc định (soft-delete aware nếu `BaseModel` dùng `SoftDeleteModel`) — nên `not exists()` sau xoá đúng.

- [ ] **Step 2: Chạy** → FAIL 404 (route chưa có).
- [ ] **Step 3: Cài đặt `serializers.py`:**

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

from django.conf import settings
from rest_framework import serializers

from plane.db.models import IssueType

ICON_NAME = re.compile(r"^[A-Za-z0-9]{1,64}$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_logo_props(value):
    # ponytail: icon names are checked by shape only; the full whitelist lives in the frontend picker
    if value in (None, {}):
        return {}
    if not isinstance(value, dict) or set(value) - {"in_use", "icon", "emoji"}:
        raise serializers.ValidationError("Invalid logo_props")
    if value.get("in_use") not in ("icon", "emoji", None):
        raise serializers.ValidationError("Invalid logo_props")
    icon = value.get("icon")
    if icon is not None:
        if not isinstance(icon, dict) or set(icon) - {"name", "color", "background_color"}:
            raise serializers.ValidationError("Invalid icon")
        if "name" in icon and not (isinstance(icon["name"], str) and ICON_NAME.match(icon["name"])):
            raise serializers.ValidationError("Invalid icon name")
        for key in ("color", "background_color"):
            if key in icon and not (isinstance(icon[key], str) and HEX.match(icon[key])):
                raise serializers.ValidationError(f"Invalid {key}")
    emoji = value.get("emoji")
    if emoji is not None:
        if not isinstance(emoji, dict) or set(emoji) - {"value", "url"}:
            raise serializers.ValidationError("Invalid emoji")
        if any(not isinstance(v, str) or len(v) > 512 for v in emoji.values()):
            raise serializers.ValidationError("Invalid emoji")
    return value


class IssueTypeSerializer(serializers.ModelSerializer):
    level = serializers.IntegerField(min_value=0, max_value=9)
    is_preset = serializers.SerializerMethodField()

    class Meta:
        model = IssueType
        fields = ["id", "name", "description", "logo_props", "is_epic", "is_default", "is_active", "level", "is_preset"]
        read_only_fields = ["id", "is_default", "is_preset"]

    def get_is_preset(self, obj):
        return obj.external_source == "plane-work-item-types"

    def validate_logo_props(self, value):
        return validate_logo_props(value)

    def validate_name(self, value):
        value = value.strip()
        qs = IssueType.objects.filter(workspace=self.context["workspace"], name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A work item type with this name already exists")
        return value

    def validate(self, attrs):
        if not self.instance:
            cap = getattr(settings, "WORK_ITEM_TYPES_MAX", 50)
            if IssueType.objects.filter(workspace=self.context["workspace"]).count() >= cap:
                raise serializers.ValidationError(f"At most {cap} work item types are allowed")
        return attrs
```

`views.py` (phần workspace):

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, IssueType, ProjectIssueType, Workspace
from plane.ee.work_item_types.serializers import IssueTypeSerializer
from plane.utils.permissions.workspace import WorkspaceOwnerPermission, WorkspaceViewerPermission


class _WorkspaceTypeBase(BaseAPIView):
    def get_permissions(self):
        cls = WorkspaceViewerPermission if self.request.method == "GET" else WorkspaceOwnerPermission
        return [cls()]

    def workspace(self, slug):
        return get_object_or_404(Workspace, slug=slug)


class WorkItemTypeListEndpoint(_WorkspaceTypeBase):
    def get(self, request, slug):
        qs = IssueType.objects.filter(workspace__slug=slug).order_by("-level", "name")
        return Response(IssueTypeSerializer(qs, many=True).data)

    def post(self, request, slug):
        ws = self.workspace(slug)
        serializer = IssueTypeSerializer(data=request.data, context={"workspace": ws})
        serializer.is_valid(raise_exception=True)
        serializer.save(workspace=ws)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WorkItemTypeDetailEndpoint(_WorkspaceTypeBase):
    def _get(self, slug, pk):
        return get_object_or_404(IssueType, pk=pk, workspace__slug=slug)

    def get(self, request, slug, pk):
        return Response(IssueTypeSerializer(self._get(slug, pk)).data)

    def patch(self, request, slug, pk):
        obj = self._get(slug, pk)
        locked = {"level", "is_epic"} & set(request.data)
        if locked and (
            IssueTypeSerializer().get_is_preset(obj) or Issue.objects.filter(type=obj).exists()
        ):
            return Response(
                {"error": "level and epic flag cannot change for preset types or types in use"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = IssueTypeSerializer(
            obj, data=request.data, partial=True, context={"workspace": self.workspace(slug)}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, slug, pk):
        obj = self._get(slug, pk)
        if IssueTypeSerializer().get_is_preset(obj) or obj.is_default:
            return Response({"error": "This type cannot be deleted"}, status=status.HTTP_409_CONFLICT)
        in_use = Issue.objects.filter(type=obj)
        count = in_use.count()
        target_id = request.query_params.get("migrate_to")
        if count and not target_id:
            return Response(
                {"error": "Work items use this type; pass migrate_to", "count": count},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            if count:
                target = get_object_or_404(
                    IssueType.objects.exclude(pk=obj.pk), pk=target_id, workspace__slug=slug, is_active=True
                )
                in_use.update(type=target)
            ProjectIssueType.objects.filter(issue_type=obj).delete()
            obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

> Nếu `BaseAPIView.initial`/`dispatch` đòi `workspace_slug` từ `kwargs["slug"]`, URL dùng `<str:slug>` như core. `in_use.update(...)` bỏ qua `pre_save` (chủ ý: migrate hàng loạt không validate cha/con). Nếu type thay thế khác level, quan hệ cha-con cũ có thể lệch — chấp nhận; **thêm kiểm tra cùng level** (`target.level == obj.level`, nếu khác trả 400 "migrate_to must have the same level") để giữ quy tắc. Viết test cho nhánh này.

`urls.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import WorkItemTypeDetailEndpoint, WorkItemTypeListEndpoint

urlpatterns = [
    path("", WorkItemTypeListEndpoint.as_view(), name="ee-work-item-types"),
    path("<uuid:pk>/", WorkItemTypeDetailEndpoint.as_view(), name="ee-work-item-type"),
]
```

`plane/ee/urls.py` — thêm route (giữ route SSO hiện có):

```python
urlpatterns = [
    path("auth/sso/", include("plane.ee.sso.urls")),
    path("api/workspaces/<str:slug>/work-item-types/", include("plane.ee.work_item_types.urls")),
    *core_urlpatterns,
]
```

- [ ] **Step 4: Bổ sung test cùng level cho `migrate_to`:**

```python
@pytest.mark.contract
def test_migrate_to_must_match_level(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=custom, created_by=create_user)
    r = session_client.delete(f"{base(workspace)}{custom.id}/?migrate_to={seeded['epic'].id}")
    assert r.status_code == 400
```

và thêm vào `delete` trước `in_use.update`: `if target.level != obj.level: return Response({"error": "migrate_to must have the same level"}, status=400)` (đặt trong `with transaction.atomic()` sau khi lấy `target`; `return` trong `atomic` là hợp lệ).
- [ ] **Step 5: Chạy** `pytest plane/tests/unit/ee/work_item_types/test_workspace_api.py -v` → PASS.
- [ ] **Step 6: Commit** — `feat(ee): workspace work item type API`.

---

### Task 5: Endpoint project (process, gán/bỏ gán, default)

**Files:**
- Modify: `plane/ee/work_item_types/views.py`, `plane/ee/work_item_types/urls.py` (thêm `project_urlpatterns`), `plane/ee/urls.py`
- Test: `plane/tests/unit/ee/work_item_types/test_project_api.py`

**Interfaces:**
- Consumes: `apply_process`, `project_process`, `ProcessChangeBlocked` (Task 2).
- Produces (prefix `/api/workspaces/<slug>/projects/<uuid:project_id>/work-item-types/`):
  - `GET` → `{"process": "scrum"|"agile"|None, "enabled": bool, "types": [IssueTypeSerializer + "is_project_default"]}` (quyền: `ProjectLitePermission`/thành viên — dùng `ProjectEntityPermission` cho GET).
  - `POST {"process": "scrum"|"agile"}` → áp process (`ProjectAdminPermission`); `ProcessChangeBlocked` → 409; process không hợp lệ → 400.
  - `POST assign/ {"type_id": uuid}` → gán type workspace vào project (type phải cùng workspace, `is_active`; 400 chung "Invalid work item type" nếu không); `DELETE assign/<uuid:type_id>/` → bỏ gán; nếu có issue dùng → 409; type default của project → 409.
  - `POST default/ {"type_id": uuid}` → đặt default (type phải đã gán).

- [ ] **Step 1: Viết test fail** — `test_project_api.py`:

```python
import pytest

from plane.db.models import Issue, IssueType, ProjectIssueType, State, User, Workspace
from plane.ee.work_item_types.seed import apply_process, seed_types


def url(ws, p, tail=""):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/work-item-types/{tail}"


@pytest.mark.contract
def test_apply_process_then_get(session_client, workspace, project):
    r = session_client.post(url(workspace, project), {"process": "agile"}, format="json")
    assert r.status_code == 200, r.content
    body = session_client.get(url(workspace, project)).json()
    assert body["process"] == "agile" and body["enabled"] is True
    assert "User Story" in {t["name"] for t in body["types"]}


@pytest.mark.contract
def test_invalid_process(session_client, workspace, project):
    assert session_client.post(url(workspace, project), {"process": "kanban"}, format="json").status_code == 400


@pytest.mark.contract
def test_switch_blocked_returns_409(session_client, workspace, project, create_user):
    apply_process(project, "scrum")
    pbi = IssueType.objects.get(workspace=workspace, external_id="product_backlog_item")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=pbi, created_by=create_user)
    assert session_client.post(url(workspace, project), {"process": "agile"}, format="json").status_code == 409


@pytest.mark.contract
def test_non_admin_cannot_apply(api_client, workspace, project):
    from plane.db.models import ProjectMember, WorkspaceMember

    m = User.objects.create(email="m@plane.so")
    WorkspaceMember.objects.create(workspace=workspace, member=m, role=15)
    ProjectMember.objects.create(project=project, member=m, workspace=workspace, role=15)
    api_client.force_authenticate(user=m)
    assert api_client.post(url(workspace, project), {"process": "scrum"}, format="json").status_code == 403
    assert api_client.get(url(workspace, project)).status_code == 200


@pytest.mark.contract
def test_assign_and_unassign_custom_type(session_client, workspace, project):
    apply_process(project, "scrum")
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    assert session_client.post(url(workspace, project, "assign/"), {"type_id": str(custom.id)}, format="json").status_code == 200
    assert ProjectIssueType.objects.filter(project=project, issue_type=custom).exists()
    assert session_client.delete(url(workspace, project, f"assign/{custom.id}/")).status_code == 204


@pytest.mark.contract
def test_assign_foreign_type_rejected_generic(session_client, workspace, project, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=1)
    r = session_client.post(url(workspace, project, "assign/"), {"type_id": str(foreign.id)}, format="json")
    assert r.status_code == 400 and "Invalid work item type" in str(r.json())


@pytest.mark.contract
def test_cannot_unassign_default_or_in_use(session_client, workspace, project, create_user):
    apply_process(project, "scrum")
    types = {t.external_id: t for t in IssueType.objects.filter(workspace=workspace)}
    assert session_client.delete(url(workspace, project, f"assign/{types['product_backlog_item'].id}/")).status_code == 409
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=types["task"], created_by=create_user)
    assert session_client.delete(url(workspace, project, f"assign/{types['task'].id}/")).status_code == 409


@pytest.mark.contract
def test_set_default(session_client, workspace, project):
    apply_process(project, "scrum")
    task = IssueType.objects.get(workspace=workspace, external_id="task")
    assert session_client.post(url(workspace, project, "default/"), {"type_id": str(task.id)}, format="json").status_code == 200
    assert ProjectIssueType.objects.get(project=project, is_default=True).issue_type_id == task.id
```

- [ ] **Step 2: Chạy** → FAIL 404.
- [ ] **Step 3: Cài đặt** — thêm vào `views.py` (cùng import bổ sung `ProjectIssueType, Project` đã có; thêm `ProjectAdminPermission, ProjectEntityPermission` từ `plane.utils.permissions.project`; `apply_process, project_process, ProcessChangeBlocked` từ `.seed`; `PROCESSES` từ `.presets`):

```python
class _ProjectTypeBase(BaseAPIView):
    def get_permissions(self):
        cls = ProjectEntityPermission if self.request.method == "GET" else ProjectAdminPermission
        return [cls()]

    def project_obj(self, slug, project_id):
        return get_object_or_404(Project, pk=project_id, workspace__slug=slug)

    def _valid_type(self, slug, type_id):
        try:
            return IssueType.objects.filter(pk=type_id, workspace__slug=slug, is_active=True).first()
        except (ValueError, ValidationError):
            return None


class ProjectWorkItemTypesEndpoint(_ProjectTypeBase):
    def get(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        rows = ProjectIssueType.objects.filter(project=project).select_related("issue_type")
        default_id = next((r.issue_type_id for r in rows if r.is_default), None)
        types = []
        for r in sorted(rows, key=lambda r: (-r.issue_type.level, r.issue_type.name)):
            data = IssueTypeSerializer(r.issue_type).data
            data["is_project_default"] = r.issue_type_id == default_id
            types.append(data)
        return Response(
            {"process": project_process(project), "enabled": project.is_issue_type_enabled, "types": types}
        )

    def post(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        process = request.data.get("process")
        if process not in PROCESSES:
            return Response({"error": "process must be scrum or agile"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            apply_process(project, process)
        except ProcessChangeBlocked as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"process": process}, status=status.HTTP_200_OK)


class ProjectWorkItemTypeAssignEndpoint(_ProjectTypeBase):
    def post(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        obj = self._valid_type(slug, request.data.get("type_id"))
        if obj is None:
            return Response({"error": "Invalid work item type"}, status=status.HTTP_400_BAD_REQUEST)
        ProjectIssueType.objects.get_or_create(project=project, issue_type=obj, defaults={"level": int(obj.level)})
        return Response({"type_id": str(obj.id)}, status=status.HTTP_200_OK)

    def delete(self, request, slug, project_id, type_id):
        project = self.project_obj(slug, project_id)
        row = get_object_or_404(ProjectIssueType, project=project, issue_type_id=type_id)
        if row.is_default or Issue.objects.filter(project=project, type_id=type_id).exists():
            return Response(
                {"error": "Type is the project default or still used by work items"}, status=status.HTTP_409_CONFLICT
            )
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectWorkItemTypeDefaultEndpoint(_ProjectTypeBase):
    def post(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        row = ProjectIssueType.objects.filter(project=project, issue_type_id=request.data.get("type_id")).first()
        if row is None:
            return Response({"error": "Invalid work item type"}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            ProjectIssueType.objects.filter(project=project, is_default=True).update(is_default=False)
            row.is_default = True
            row.save(update_fields=["is_default"])
        return Response(status=status.HTTP_200_OK)
```

> `request.data.get("type_id")` không hợp lệ UUID làm `filter(pk=...)` ném `ValidationError`/`ValueError` của Django — bọc `try/except (ValueError, DjangoValidationError)` trong `_valid_type` (import `from django.core.exceptions import ValidationError`) và ở `default`; kết quả trả 400 chung.

`urls.py` thêm:

```python
from .views import (
    ProjectWorkItemTypeAssignEndpoint,
    ProjectWorkItemTypeDefaultEndpoint,
    ProjectWorkItemTypesEndpoint,
    WorkItemTypeDetailEndpoint,
    WorkItemTypeListEndpoint,
)

project_urlpatterns = [
    path("", ProjectWorkItemTypesEndpoint.as_view(), name="ee-project-work-item-types"),
    path("assign/", ProjectWorkItemTypeAssignEndpoint.as_view(), name="ee-project-work-item-type-assign"),
    path("assign/<uuid:type_id>/", ProjectWorkItemTypeAssignEndpoint.as_view(), name="ee-project-work-item-type-unassign"),
    path("default/", ProjectWorkItemTypeDefaultEndpoint.as_view(), name="ee-project-work-item-type-default"),
]
```

`plane/ee/urls.py` thêm trước `*core_urlpatterns`: `path("api/workspaces/<str:slug>/projects/<uuid:project_id>/work-item-types/", include((project_urlpatterns, "ee"))),` với `from plane.ee.work_item_types.urls import project_urlpatterns`.

- [ ] **Step 4: Chạy** `pytest plane/tests/unit/ee/work_item_types/test_project_api.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(ee): project work item type API (process, assign, default)`.

---

### Task 6: Seam core — nhận/đọc `type_id`, validate sub-issue, siết public API

**Files (mỗi file là seam, thêm vào allowlist ở Task 7):**
- Modify: `apps/api/plane/app/serializers/issue.py` (IssueCreateSerializer ~dòng 87; `IssueSerializer.Meta.fields` ~dòng 798; dict `to_representation` ~dòng 855)
- Modify: `apps/api/plane/app/serializers/draft.py` (DraftIssueCreateSerializer ~dòng 38)
- Modify: `apps/api/plane/api/serializers/issue.py` (`type_id` queryset ~dòng 66)
- Modify: `apps/api/plane/app/views/issue/sub_issue.py` (~dòng 236)
- Modify: `apps/api/plane/app/views/issue/base.py` (các `.values(...)` có `"parent_id"` ~dòng 187/452/884) và `apps/api/plane/app/views/issue/sub_issue.py` (~dòng 159)
- Test: `plane/tests/unit/ee/work_item_types/test_core_seams.py`

**Interfaces:**
- Consumes: `validate_issue_write`, hook Task 3.
- Produces: `POST/PATCH /api/workspaces/<slug>/projects/<pid>/issues/` nhận `type_id`; issue list/detail/sub-issue trả `type_id`; `POST .../issues/<id>/sub-issues/` validate từng sub-issue; public API `type_id` chỉ nhận type thuộc project.

- [ ] **Step 1: Viết test fail** — `test_core_seams.py` (dùng helper `url` cho issue app API: `/api/workspaces/{slug}/projects/{pid}/issues/`):

```python
import pytest

from plane.db.models import Issue, IssueType, State
from plane.ee.work_item_types.seed import apply_process


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    types = {t.external_id: t for t in IssueType.objects.filter(workspace=workspace)}
    return state, types


def issues_url(ws, p, tail=""):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/issues/{tail}"


@pytest.mark.contract
def test_create_with_type_id_and_default(session_client, workspace, project, env):
    state, t = env
    r = session_client.post(issues_url(workspace, project), {"name": "a", "type_id": str(t["bug"].id)}, format="json")
    assert r.status_code == 201, r.content
    assert Issue.objects.get(pk=r.json()["id"]).type_id == t["bug"].id
    r = session_client.post(issues_url(workspace, project), {"name": "b"}, format="json")
    assert Issue.objects.get(pk=r.json()["id"]).type_id == t["product_backlog_item"].id


@pytest.mark.contract
def test_create_invalid_hierarchy_is_400(session_client, workspace, project, env):
    state, t = env
    epic = session_client.post(issues_url(workspace, project), {"name": "e", "type_id": str(t["epic"].id)}, format="json").json()
    r = session_client.post(
        issues_url(workspace, project), {"name": "s", "type_id": str(t["sub_task"].id), "parent_id": epic["id"]}, format="json"
    )
    assert r.status_code == 400


@pytest.mark.contract
def test_patch_change_type_validated(session_client, workspace, project, env):
    state, t = env
    pbi = session_client.post(issues_url(workspace, project), {"name": "p"}, format="json").json()
    session_client.post(
        issues_url(workspace, project), {"name": "t", "type_id": str(t["task"].id), "parent_id": pbi["id"]}, format="json"
    )
    r = session_client.patch(issues_url(workspace, project, f"{pbi['id']}/"), {"type_id": str(t["task"].id)}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_foreign_type_id_rejected(session_client, workspace, project, env, create_user):
    from plane.db.models import Workspace

    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=2)
    r = session_client.post(issues_url(workspace, project), {"name": "x", "type_id": str(foreign.id)}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_issue_list_and_detail_return_type_id(session_client, workspace, project, env):
    state, t = env
    created = session_client.post(issues_url(workspace, project), {"name": "a", "type_id": str(t["bug"].id)}, format="json").json()
    detail = session_client.get(issues_url(workspace, project, f"{created['id']}/")).json()
    assert detail["type_id"] == str(t["bug"].id)
    listed = session_client.get(issues_url(workspace, project) + "?per_page=50").json()
    rows = listed["results"] if isinstance(listed, dict) and "results" in listed else listed
    flat = rows if isinstance(rows, list) else [i for g in rows.values() for i in (g if isinstance(g, list) else [])]
    assert any(i.get("type_id") == str(t["bug"].id) for i in flat)
    assert "is_epic" not in detail


@pytest.mark.contract
def test_sub_issue_bulk_assign_validated(session_client, workspace, project, env, create_user):
    state, t = env
    epic = Issue.objects.create(name="e", workspace=workspace, project=project, state=state, type=t["epic"], created_by=create_user)
    task = Issue.objects.create(name="t", workspace=workspace, project=project, state=state, type=t["task"], created_by=create_user)
    r = session_client.post(
        issues_url(workspace, project, f"{task.id}/sub-issues/"), {"sub_issue_ids": [str(epic.id)]}, format="json"
    )
    assert r.status_code == 400  # an epic cannot become a child
    epic.refresh_from_db()
    assert epic.parent_id is None
```

> Đường dẫn sub-issues thật có thể khác (`.../issues/<id>/sub-issues/`). Mở `apps/api/plane/app/urls/issue.py` để xác nhận trước khi chạy; sửa test nếu khác.

- [ ] **Step 2: Chạy** → FAIL (type_id không nhận/đọc).
- [ ] **Step 3: Cài đặt seam (mỗi cái là thay đổi nhỏ):**
  1. `app/serializers/issue.py` — `IssueCreateSerializer`: thêm `IssueType` vào import từ `plane.db.models`, và sau `parent_id = ...`:
     ```python
     type_id = serializers.PrimaryKeyRelatedField(
         source="type", queryset=IssueType.objects.all(), required=False, allow_null=True
     )
     ```
     `IssueSerializer.Meta.fields` (dòng ~786-813): thêm `"type_id",` ngay sau `"parent_id",` (dòng ~798). Dict ở `to_representation` (dòng ~855): thêm `"type_id": instance.type_id,` sau `"parent_id": instance.parent_id,`.
  2. `app/serializers/draft.py` — `DraftIssueCreateSerializer`: thêm field `type_id` y hệt trên, import `IssueType`.
  3. `api/serializers/issue.py` (public API): đổi `queryset=IssueType.objects.all()` → `IssueType.objects.none()` và thêm ở `validate()`: tra `ProjectIssueType.objects.filter(project_id=self.context["project_id"], issue_type_id=<type id>, issue_type__is_active=True).exists()` nếu có `type`; sai → `ValidationError("Invalid work item type")`. (`pre_save` vẫn là lưới an toàn cuối.) Mở file, tìm hàm `validate` hiện có (~dòng 75+) và thêm nhánh; nếu `queryset=none()` làm mọi `type_id` bị từ chối, thay bằng giữ `.all()` và chỉ thêm kiểm tra trong `validate()`. Chọn cách giữ `.all()` + kiểm tra project (an toàn hơn về hành vi cũ).
  4. `app/views/issue/sub_issue.py` — trong `post`, trước `bulk_update`:
     ```python
     from plane.ee.work_item_types.validation import validate_issue_write  # guarded import below
     ```
     Dùng import có bảo vệ ở đầu file:
     ```python
     try:
         from plane.ee.work_item_types.validation import validate_issue_write
     except ImportError:  # plugin not installed
         validate_issue_write = None
     ```
     và trong vòng lặp gán parent:
     ```python
     for sub_issue in sub_issues:
         sub_issue.parent = parent_issue
         if validate_issue_write:
             try:
                 validate_issue_write(sub_issue)
             except ValidationError as e:  # rest_framework.exceptions.ValidationError
                 return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
     ```
     (thêm `from rest_framework.exceptions import ValidationError` nếu chưa có; không gọi `validate_issue_write` cho cả lô trước khi thay đổi gì — dùng danh sách tạm để không gán dở: gán `parent` vào bản sao trong vòng lặp validate, và chỉ `bulk_update` khi tất cả hợp lệ. Cách đơn giản: validate trong vòng lặp thứ nhất, `return 400` ngay khi có lỗi; `bulk_update` ở dưới chỉ chạy khi vòng lặp xong.)
  5. `.values(...)`: chạy `grep -n '"parent_id"' apps/api/plane/app/views/issue/base.py apps/api/plane/app/views/issue/sub_issue.py` và thêm `"type_id",` ngay sau mỗi `"parent_id",` nằm trong danh sách `.values(` (không đụng chỗ khác). `type_id` là cột trực tiếp của `Issue` nên `.values` hợp lệ. Không thêm `is_epic`.
  6. `draft.py` view `create_draft_to_issue`: không cần sửa (body đã đi vào `IssueCreateSerializer` có `type_id`).
- [ ] **Step 4: Chạy** `pytest plane/tests/unit/ee/work_item_types -v` → PASS.
- [ ] **Step 5: Hồi quy core** — `pytest plane/tests/contract plane/tests/unit -q --ds=plane.settings.ee_test` và cả `--ds=plane.settings.test` (không có plugin) → không hỏng; import có bảo vệ giữ core chạy khi không cài plugin. Nếu một test core hỏng vì thêm `type_id` vào response, sửa snapshot của test đó và ghi lại trong commit.
- [ ] **Step 6: Commit** — `feat: accept and return type_id on issues, validate sub-issue assignment`.

---

### Task 7: Allowlist + guard + kiểm tra cuối

**Files:**
- Modify: `deployments/ee/core-allowlist.txt` (thêm các seam của Task 6 vào cuối phần "known core seam edits")
- Test: chạy guard + toàn bộ suite EE

- [ ] **Step 1: Thêm vào allowlist:**

```
apps/api/plane/app/serializers/issue.py
apps/api/plane/app/serializers/draft.py
apps/api/plane/api/serializers/issue.py
apps/api/plane/app/views/issue/base.py
apps/api/plane/app/views/issue/sub_issue.py
```

(Các file `plane/ee/*` và `plane/tests/unit/ee/*` đã nằm trong allowlist; plan và spec ở `docs/superpowers/*` cũng đã có.)

- [ ] **Step 2: Chạy guard** — `BASE=origin/preview sh deployments/ee/check-core-untouched.sh` → `OK: only plugin-owned and allow-listed files changed.` Nếu `origin/preview` chưa có, `git fetch origin preview` trước.
- [ ] **Step 3: Chạy toàn bộ** — `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee` và suite core không plugin `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m "unit or contract" -q`. Cả hai xanh.
- [ ] **Step 4: Commit** — `chore(ee): allow-list work item type seams`.

---

## Self-review (đối chiếu spec)
- Preset Scrum/Agile + process theo project, suy ra từ type: Task 2. Quy tắc phân cấp, cycle, default, chỉ validate khi đổi, IDOR chung, kiểm cha cùng project: Task 1, 3. Hook `pre_save` không sửa core: Task 3. CRUD type, giới hạn 50, trùng tên, `logo_props`, xoá `migrate_to` (thêm yêu cầu cùng level), cấm đổi level khi đang dùng/preset, quyền Admin: Task 4. Gán/bỏ gán/default/đổi process, 409: Task 5. `type_id` ghi/đọc, validate bulk sub-issue, draft→issue, siết public API: Task 6. Allowlist + guard: Task 7.
- **Không có endpoint "đổi type" riêng**: `PATCH issue` với `type_id` đã đi qua `pre_save` (kiểm cha và con) — thay đổi so với spec, đúng tinh thần YAGNI; Plan 2 dùng PATCH hiện có.
- **Chưa phủ (chủ ý)**: chuyển issue giữa project (core chưa có luồng — spec đã ghi cần map type; để Plan sau nếu tìm thấy luồng), filter Type ở rich filters, toàn bộ UI → Plan 2. `ProjectIssueType.deleted_at` được `ProjectIssueType.objects` lọc theo manager mặc định.
- Rủi ro cần quan sát khi chạy: (1) `pre_save` thêm 1 query/lần save Issue; (2) `IssueType.objects.filter(...).only(...)[:200]` trong `validate_issue_write`; (3) đường URL sub-issues và `BaseAPIView` yêu cầu `kwargs["slug"]`; (4) tên icon lucide của preset (Zap, Layers, Bug, CheckSquare, ListTree, BookOpen) phải khớp `LUCIDE_ICONS_LIST` ở `packages/blocks/src/emoji-icon-picker/lucide-icons.tsx` — kiểm tra ở Task 2 và đổi tên nếu thiếu.
