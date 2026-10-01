# Work Item Types — Frontend Implementation Plan (Plan 2/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UI cho work item types: chọn type khi tạo work item (icon + màu, mờ type không hợp lệ theo cha), badge type ở mọi nơi hiển thị identifier, đổi type trong detail/peek, filter `Type` trong rich filters, màn Workspace Settings (CRUD type) và tab Project Settings (Scrum/Agile, gán type, default, bật/tắt).

**Architecture:** Toàn bộ logic mới ở `apps/web/ee/work-item-types/` (service, store MobX singleton, hook, component, page, filter config). Logic thuần (phân cấp, chọn mặc định, gợi ý type con, localStorage) nằm trong `rules.ts` không phụ thuộc runtime nào để test bằng vitest. Core chỉ có seam một-hai dòng: badge gắn vào **một** component dùng chung `IssueIdentifier` (phủ list/kanban/spreadsheet/calendar/gantt/peek/sub-issues/parent), select gắn vào `default-properties.tsx`, route qua `app/routes/extended.ts`, mục sidebar qua constants settings.

**Tech Stack:** React 19 + react-router 7 (framework mode), MobX 6 + mobx-react, SWR, react-hook-form (`FormProvider` có sẵn trong `issue-modal/form.tsx`), `@makeplane/propel` (Menu, Tooltip, Dialog, Button, Switch, InputField, PillChrome), `@plane/blocks` (`Logo`, `EmojiPicker`, `setToast`), `@plane/i18n` (i18next + ICU), vitest 4 (catalog), oxlint/oxfmt, pnpm.

**Spec:** `docs/superpowers/specs/2026-10-01-work-item-types-design.md`. Backend: Plan 1 `docs/superpowers/plans/2026-10-01-work-item-types-backend.md` (đã xong).

## Global Constraints
- API (session auth, base `/api/workspaces/<slug>/`): `work-item-types/` GET/POST, `work-item-types/<id>/` GET/PATCH/DELETE (`?migrate_to=<id>`; 409 `{error,count}`); `projects/<pid>/work-item-types/` GET → `{process, enabled, types:[...type, is_project_default]}`, POST `{process}`; `.../assign/` POST `{type_id}`; `.../assign/<type_id>/` DELETE; `.../default/` POST `{type_id}`. Lỗi type sai: 400 `{"error":"Invalid work item type"}`; lỗi issue: 400 `{type_id:[...]}` / `{parent_id:[...]}`.
- Issue chỉ có `type_id`, **không có `is_epic`** → web luôn đi luồng `EIssueServiceType.ISSUES`. Biết type là Epic qua store (`isEpic`). Không thêm route/service `/epics/`.
- Quy tắc phân cấp phía client chỉ để **lọc/mờ**, server là nguồn sự thật: `child.level < parent.level`; Epic không có cha; `level 0` cần cha với `level ∈ {1,2}`. `type_id = null` (issue cũ) = type mặc định của project.
- Icon type dùng **lucide** (`Logo type="lucide"`, `EmojiPicker iconType="lucide" showEmojiTab={false}`) vì backend chỉ nhận tên `^[A-Za-z0-9]{1,64}$` (tên material có `_`). Preset backend dùng `Epic, Layers, AlertTriangle, CheckSquare, List, BookOpen`.
- Tên preset dịch theo `external_id` (Task 1 thêm `external_id` vào payload): key `work_item_types.ee.preset.<external_id>`; type tuỳ biến hiển thị nguyên văn.
- Tải type lỗi / project chưa bật → ẩn select & badge, **không chặn** tạo issue. Đổi type lỗi → toast, giữ giá trị cũ.
- localStorage chỉ để nhớ type gần nhất theo project, mọi truy cập bọc `try/catch`.
- Mọi file mới bắt đầu bằng header:
  ```ts
  /**
   * Copyright (c) 2023-present Plane Software, Inc. and contributors
   * SPDX-License-Identifier: AGPL-3.0-only
   * See the LICENSE file for details.
   */
  ```
  (Python: 3 dòng `#` tương đương.) Các khối code bên dưới **bỏ qua header cho gọn — implementer phải thêm** vào đầu mỗi file mới.
- Mọi file core bị sửa phải có trong `deployments/ee/core-allowlist.txt` (mục "known core seam edits") trong **cùng task**.
- Kiểm tra mỗi task (từ gốc repo): `pnpm turbo run check:types --filter=web` , `pnpm turbo run check:lint --filter=web`, `pnpm fix:format` (task đụng package khác thì thêm `--filter=@plane/types` / `@plane/constants` / `@plane/i18n`). Test frontend: `pnpm --filter web test`.
- Không có `node_modules` trong worktree: chạy `pnpm install` một lần trước Task 2.

## File Structure
| File | Trách nhiệm |
|---|---|
| `apps/web/ee/vitest.config.ts` | config vitest riêng cho `ee/**` (không nạp `vite.config.ts` có plugin react-router) |
| `packages/types/src/work-item-types.ts` | `TIssueType`, `TProjectIssueType`, `TProjectWorkItemTypes`, `TWorkItemProcess` |
| `apps/web/ee/work-item-types/rules.ts` | hàm thuần: `hierarchyReason`, `typeOptionsForParent`, `suggestedChildTypeId`, `defaultTypeId`, `initialTypeId`, `presetLabelKey`, `read/writeLastTypeId`, `firstErrorMessage` |
| `apps/web/ee/work-item-types/work-item-types.test.ts` | test vitest cho rules + store |
| `apps/web/ee/work-item-types/service.ts` | `WorkItemTypeService extends APIService` |
| `apps/web/ee/work-item-types/store.ts` | `WorkItemTypeStore` (MobX), nhận service qua constructor |
| `apps/web/ee/work-item-types/hooks.ts` | singleton store, `useWorkItemTypes`, `useProjectWorkItemTypes`, `useWorkspaceWorkItemTypes`, `useParentIssueFilter` |
| `apps/web/ee/work-item-types/components/type-name.ts` | `useTypeName()` (preset i18n / tên nguyên văn) |
| `apps/web/ee/work-item-types/components/issue-type-badge.tsx` | badge icon + tooltip/aria-label |
| `apps/web/ee/work-item-types/components/issue-type-select.tsx` | dropdown chọn type (mờ + lý do), tự chọn mặc định / theo cha |
| `apps/web/ee/work-item-types/components/issue-type-form-field.tsx` | gắn select vào `FormProvider` của modal (setValue không làm dirty khi tự chọn) |
| `apps/web/ee/work-item-types/components/issue-type-change.tsx` | đổi type issue có sẵn qua `updateIssue` |
| `apps/web/ee/work-item-types/filter-config.tsx` | `useWorkItemTypeFilterConfig` cho rich filters |
| `apps/web/ee/work-item-types/components/type-form-dialog.tsx` | dialog tạo/sửa type (icon, màu, nền, level, epic) |
| `apps/web/ee/work-item-types/components/type-delete-dialog.tsx` | dialog xoá + `migrate_to` |
| `apps/web/ee/work-item-types/pages/workspace-settings.tsx` | trang Workspace Settings |
| `apps/web/ee/work-item-types/pages/project-settings.tsx` | trang Project Settings |
| `packages/i18n/src/locales/{en,vi-VN}/work-item-type.json` | khối `work_item_types.ee.*` |

---

### Task 1: Backend nhỏ phục vụ frontend (`external_id`, filter `type_id`)

Quyết định: thêm `external_id` vào payload (không đoán preset theo tên — tên bị admin đổi được).

**Files:**
- Modify: `apps/api/plane/ee/work_item_types/serializers.py` (plugin-owned)
- Modify: `apps/api/plane/utils/filters/filterset.py` (core seam)
- Modify: `deployments/ee/core-allowlist.txt`
- Create: `apps/api/plane/tests/unit/ee/work_item_types/test_frontend_support.py`

**Interfaces:**
- Produces: type payload có `external_id: str | null` (read-only); `IssueFilterSet` nhận `type_id` và `type_id__in`.

- [ ] **Step 1: Viết test fail** — `test_frontend_support.py`:

```python
import pytest

from plane.db.models import Issue, IssueType, State
from plane.ee.work_item_types.seed import apply_process
from plane.ee.work_item_types.serializers import IssueTypeSerializer
from plane.utils.filters.filterset import IssueFilterSet


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    types = {t.external_id: t for t in IssueType.objects.filter(workspace=workspace)}
    return state, types


@pytest.mark.unit
def test_external_id_is_exposed_and_read_only(env):
    _, t = env
    data = IssueTypeSerializer(t["epic"]).data
    assert data["external_id"] == "epic"
    assert "external_id" in IssueTypeSerializer.Meta.read_only_fields


@pytest.mark.unit
def test_filter_by_type_id(env, workspace, project, create_user):
    state, t = env
    mk = lambda n, ty: Issue.objects.create(  # noqa: E731
        name=n, workspace=workspace, project=project, state=state, type=ty, created_by=create_user
    )
    epic, task, bug = mk("e", t["epic"]), mk("t", t["task"]), mk("b", t["bug"])
    base = Issue.issue_objects.filter(project=project)
    one = IssueFilterSet(data={"type_id": str(t["epic"].id)}, queryset=base).qs
    assert set(one.values_list("id", flat=True)) == {epic.id}
    many = IssueFilterSet(data={"type_id__in": f"{t['task'].id},{t['bug'].id}"}, queryset=base).qs
    assert set(many.values_list("id", flat=True)) == {task.id, bug.id}
```

- [ ] **Step 2: Chạy, xác nhận fail** — `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/work_item_types/test_frontend_support.py` → FAIL (`KeyError: 'external_id'`, filter bị bỏ qua).

- [ ] **Step 3: Cài đặt**
  1. `serializers.py`, `IssueTypeSerializer.Meta`: thêm `"external_id"` vào **cuối** list `fields` hiện có và vào `read_only_fields` (giữ nguyên các field khác, kể cả `low_contrast` nếu đã có).
  2. `filterset.py`, trong `class IssueFilterSet`, ngay dưới khối `state_id`:
     ```python
     type_id = filters.UUIDFilter(field_name="type_id")
     type_id__in = UUIDInFilter(field_name="type_id", lookup_expr="in")
     ```
     Ghi chú cố ý: issue cũ `type=null` không khớp filter Type (spec coi null là mặc định lúc đọc) — chấp nhận, ghi trong Self-review.
  3. `core-allowlist.txt`: thêm `apps/api/plane/utils/filters/filterset.py`.
- [ ] **Step 4: Chạy lại** → PASS; chạy cả `sh bin/run-ee-tests.sh plane/tests/unit/ee/work_item_types` → PASS.
- [ ] **Step 5: Commit** — `git add apps/api/plane/ee/work_item_types/serializers.py apps/api/plane/utils/filters/filterset.py apps/api/plane/tests/unit/ee/work_item_types/test_frontend_support.py deployments/ee/core-allowlist.txt && git commit -m "feat(wit): expose external_id and filter issues by type_id"`.

---

### Task 2: Hạ tầng test vitest cho `apps/web/ee`

`apps/web` chưa có test runner (chỉ `packages/blocks`, `packages/services`, `apps/live` có vitest). Thêm tối thiểu, config đặt trong `ee/` để không chạm `vite.config.ts`.

**Files:**
- Modify: `apps/web/package.json` (core seam), `pnpm-lock.yaml` (do `pnpm install` sinh ra)
- Create: `apps/web/ee/vitest.config.ts`
- Modify: `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Produces: `pnpm --filter web test` chạy `ee/**/*.test.ts` ở môi trường node.

- [ ] **Step 1:** `apps/web/package.json` — thêm script `"test": "vitest run --config ee/vitest.config.ts"` (sau `fix:format`) và devDependency `"vitest": "catalog:"` (giữ thứ tự alphabet, sau `vite-tsconfig-paths`).
- [ ] **Step 2:** `apps/web/ee/vitest.config.ts`:

```ts
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Own config so vitest does not load apps/web/vite.config.ts (the react-router plugin breaks under vitest).
export default defineConfig({
  test: {
    root: fileURLToPath(new URL("..", import.meta.url)),
    include: ["ee/**/*.test.ts"],
    environment: "node",
  },
});
```

- [ ] **Step 3:** `pnpm install` (cập nhật `pnpm-lock.yaml`), rồi `pnpm --filter web test` → vitest báo "No test files found" và exit 1 — đúng mong đợi ở bước này (Task 4 thêm test đầu tiên); chứng tỏ config được nạp mà không đụng `vite.config.ts`.
- [ ] **Step 4:** allowlist thêm:
  ```
  apps/web/package.json
  pnpm-lock.yaml
  ```
- [ ] **Step 5:** `pnpm turbo run check:types --filter=web` → PASS.
- [ ] **Step 6: Commit** — `chore(ee): vitest runner for apps/web/ee`.

---

### Task 3: Kiểu dữ liệu `@plane/types`

**Files:**
- Create: `packages/types/src/work-item-types.ts`
- Modify: `packages/types/src/index.ts`, `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Produces: `TWorkItemProcess`, `TIssueType`, `TProjectIssueType`, `TProjectWorkItemTypes`, `TIssueTypeConflict`.

- [ ] **Step 1:** `packages/types/src/work-item-types.ts`:

```ts
import type { TLogoProps } from "./common";

export type TWorkItemProcess = "scrum" | "agile";

export type TIssueType = {
  id: string;
  name: string;
  description: string;
  logo_props: TLogoProps;
  is_epic: boolean;
  is_default: boolean;
  is_active: boolean;
  /** 0..9 — a parent must have a higher level than its child; 0 is a sub-task. */
  level: number;
  is_preset: boolean;
  /** Preset key ("epic", "user_story", …) or null for custom types. */
  external_id: string | null;
  /** Icon colour vs background contrast below 4.5:1. */
  low_contrast?: boolean;
};

export type TProjectIssueType = TIssueType & { is_project_default: boolean };

export type TProjectWorkItemTypes = {
  /** null = assigned types match neither preset process ("custom"). */
  process: TWorkItemProcess | null;
  enabled: boolean;
  types: TProjectIssueType[];
};

/** 409 body of DELETE work-item-types/<id>/ */
export type TIssueTypeConflict = { error: string; count?: number };
```

- [ ] **Step 2:** `packages/types/src/index.ts` — thêm `export * from "./work-item-types";` sau dòng `export * from "./workspace-views";`.
- [ ] **Step 3:** allowlist thêm `packages/types/src/work-item-types.ts` và `packages/types/src/index.ts`.
- [ ] **Step 4:** `pnpm turbo run check:types --filter=@plane/types` → PASS (không trùng tên: `grep -rn "TIssueType\b" packages/types/src` chỉ ra file mới).
- [ ] **Step 5: Commit** — `feat(types): work item type types`.

---

### Task 4: Logic thuần `rules.ts` (TDD)

**Files:**
- Create: `apps/web/ee/work-item-types/rules.ts`, `apps/web/ee/work-item-types/work-item-types.test.ts`

**Interfaces:**
- Consumes: `TProjectIssueType` (Task 3).
- Produces:
  - `type THierarchyReason = "needs_parent" | "epic_no_parent" | "parent_level" | "subtask_parent"`
  - `hierarchyReason(child: TLevelInfo, parent: TLevelInfo | null): THierarchyReason | null`
  - `typeOptionsForParent(types, parent: TLevelInfo | null | undefined): { type; reason }[]` (`undefined` = cha chưa biết → không mờ)
  - `defaultTypeId(types): string | null`, `suggestedChildTypeId(types, parent): string | null`, `initialTypeId(types, projectId, storage?): string | null`
  - `presetLabelKey(type): string | null`, `readLastTypeId(projectId, storage?)`, `writeLastTypeId(projectId, typeId, storage?)`, `firstErrorMessage(err: unknown): string | null`

- [ ] **Step 1: Viết test fail** — `work-item-types.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { TProjectIssueType } from "@plane/types";
import {
  defaultTypeId,
  firstErrorMessage,
  hierarchyReason,
  initialTypeId,
  presetLabelKey,
  readLastTypeId,
  suggestedChildTypeId,
  typeOptionsForParent,
  writeLastTypeId,
} from "./rules";

export const mkType = (o: Partial<TProjectIssueType> & Pick<TProjectIssueType, "id" | "level">): TProjectIssueType => ({
  name: o.id,
  description: "",
  logo_props: { in_use: "icon", icon: { name: "List", color: "#64748B" } },
  is_epic: false,
  is_default: false,
  is_active: true,
  is_preset: true,
  external_id: o.id,
  is_project_default: false,
  ...o,
});

const EPIC = mkType({ id: "epic", level: 4, is_epic: true });
const FEATURE = mkType({ id: "feature", level: 3 });
const STORY = mkType({ id: "user_story", level: 2, is_project_default: true });
const BUG = mkType({ id: "bug", level: 2 });
const TASK = mkType({ id: "task", level: 1 });
const SUB = mkType({ id: "sub_task", level: 0 });
const ALL = [SUB, TASK, BUG, STORY, FEATURE, EPIC];

class MemoryStorage {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
}
const throwing = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("QuotaExceededError");
  },
};

describe("hierarchyReason (mirror of backend rules.py)", () => {
  it.each([
    [FEATURE, EPIC],
    [STORY, FEATURE],
    [STORY, EPIC],
    [TASK, STORY],
    [TASK, BUG],
    [SUB, TASK],
    [SUB, STORY],
    [EPIC, null],
    [STORY, null],
  ])("allows %o under %o", (child, parent) => {
    expect(hierarchyReason(child, parent)).toBeNull();
  });

  it("rejects with a reason", () => {
    expect(hierarchyReason(EPIC, FEATURE)).toBe("epic_no_parent");
    expect(hierarchyReason(STORY, STORY)).toBe("parent_level");
    expect(hierarchyReason(STORY, TASK)).toBe("parent_level");
    expect(hierarchyReason(SUB, EPIC)).toBe("subtask_parent");
    expect(hierarchyReason(SUB, FEATURE)).toBe("subtask_parent");
    expect(hierarchyReason(SUB, null)).toBe("needs_parent");
  });
});

describe("typeOptionsForParent", () => {
  it("sorts by level desc, hides inactive, mutes invalid types", () => {
    const off = mkType({ id: "off", level: 1, is_active: false });
    const opts = typeOptionsForParent([...ALL, off], STORY);
    expect(opts.map((o) => o.type.id)).toEqual(["epic", "feature", "bug", "user_story", "task", "sub_task"]);
    expect(opts.filter((o) => o.reason === null).map((o) => o.type.id)).toEqual(["task", "sub_task"]);
  });
  it("does not mute anything when the parent type is unknown", () => {
    expect(typeOptionsForParent(ALL, undefined).every((o) => o.reason === null)).toBe(true);
  });
  it("mutes only sub-task when there is no parent", () => {
    const muted = typeOptionsForParent(ALL, null).filter((o) => o.reason);
    expect(muted.map((o) => o.type.id)).toEqual(["sub_task"]);
  });
});

describe("defaults", () => {
  it("defaultTypeId is the project default", () => {
    expect(defaultTypeId(ALL)).toBe("user_story");
    expect(defaultTypeId([TASK])).toBeNull();
  });
  it.each([
    [EPIC, "feature"],
    [FEATURE, "user_story"],
    [STORY, "task"],
    [BUG, "task"],
    [TASK, "sub_task"],
    [SUB, null],
  ])("suggests the level right below %o", (parent, expected) => {
    expect(suggestedChildTypeId(ALL, parent)).toBe(expected);
  });
  it("initialTypeId prefers the remembered type while it is still active", () => {
    const s = new MemoryStorage();
    expect(initialTypeId(ALL, "p1", s)).toBe("user_story");
    writeLastTypeId("p1", "bug", s);
    expect(initialTypeId(ALL, "p1", s)).toBe("bug");
    writeLastTypeId("p1", "gone", s);
    expect(initialTypeId(ALL, "p1", s)).toBe("user_story");
  });
  it("never throws when storage is blocked", () => {
    expect(readLastTypeId("p1", throwing)).toBeNull();
    expect(() => writeLastTypeId("p1", "bug", throwing)).not.toThrow();
    expect(initialTypeId(ALL, "p1", throwing)).toBe("user_story");
  });
});

describe("labels and errors", () => {
  it("presetLabelKey only for presets", () => {
    expect(presetLabelKey(EPIC)).toBe("work_item_types.ee.preset.epic");
    expect(presetLabelKey(mkType({ id: "spike", level: 1, is_preset: false, external_id: null }))).toBeNull();
  });
  it("firstErrorMessage reads DRF bodies", () => {
    expect(firstErrorMessage({ type_id: ["Invalid work item type"] })).toBe("Invalid work item type");
    expect(firstErrorMessage({ error: "This type cannot be deleted", count: 3 })).toBe("This type cannot be deleted");
    expect(firstErrorMessage(undefined)).toBeNull();
  });
});
```

- [ ] **Step 2: Chạy, xác nhận fail** — `pnpm --filter web test` → FAIL `Cannot find module './rules'`.

- [ ] **Step 3: Cài đặt** — `rules.ts`:

```ts
import type { TIssueType, TProjectIssueType } from "@plane/types";

// Mirror of apps/api/plane/ee/work_item_types/rules.py — used only to filter/mute choices; the server decides.
const SUBTASK_PARENT_LEVELS = new Set([1, 2]);

export type THierarchyReason = "needs_parent" | "epic_no_parent" | "parent_level" | "subtask_parent";
type TLevelInfo = Pick<TIssueType, "level" | "is_epic">;
type TStorage = Pick<Storage, "getItem" | "setItem">;

export function hierarchyReason(child: TLevelInfo, parent: TLevelInfo | null): THierarchyReason | null {
  if (!parent) return child.level === 0 ? "needs_parent" : null;
  if (child.is_epic) return "epic_no_parent";
  if (child.level >= parent.level) return "parent_level";
  if (child.level === 0 && !SUBTASK_PARENT_LEVELS.has(parent.level)) return "subtask_parent";
  return null;
}

export type TTypeOption = { type: TProjectIssueType; reason: THierarchyReason | null };

/** `parent === undefined` means "parent type unknown": nothing is muted. */
export function typeOptionsForParent(
  types: TProjectIssueType[],
  parent: TLevelInfo | null | undefined
): TTypeOption[] {
  return types
    .filter((type) => type.is_active)
    .toSorted((a, b) => b.level - a.level || a.name.localeCompare(b.name))
    .map((type) => ({ type, reason: parent === undefined ? null : hierarchyReason(type, parent) }));
}

export const defaultTypeId = (types: TProjectIssueType[]): string | null =>
  types.find((type) => type.is_project_default)?.id ?? null;

/** Epic→Feature, Feature→PBI/Story (project default wins ties), Story/Bug→Task, Task→Sub-task. */
export function suggestedChildTypeId(types: TProjectIssueType[], parent: TLevelInfo): string | null {
  const valid = typeOptionsForParent(types, parent).filter((o) => o.reason === null && !o.type.is_epic);
  if (!valid.length) return null;
  const top = valid[0].type.level;
  const sameLevel = valid.filter((o) => o.type.level === top);
  return (sameLevel.find((o) => o.type.is_project_default) ?? sameLevel[0]).type.id;
}

const lastTypeKey = (projectId: string) => `plane:wit:last-type:${projectId}`;

export function readLastTypeId(projectId: string, storage?: TStorage): string | null {
  try {
    return (storage ?? globalThis.localStorage)?.getItem(lastTypeKey(projectId)) ?? null;
  } catch {
    return null; // private mode / blocked site data: remembering is best-effort
  }
}

export function writeLastTypeId(projectId: string, typeId: string, storage?: TStorage): void {
  try {
    (storage ?? globalThis.localStorage)?.setItem(lastTypeKey(projectId), typeId);
  } catch {
    // best-effort, see readLastTypeId
  }
}

export function initialTypeId(types: TProjectIssueType[], projectId: string, storage?: TStorage): string | null {
  const last = readLastTypeId(projectId, storage);
  if (last && types.some((type) => type.id === last && type.is_active)) return last;
  return defaultTypeId(types);
}

export const presetLabelKey = (type: Pick<TIssueType, "is_preset" | "external_id">): string | null =>
  type.is_preset && type.external_id ? `work_item_types.ee.preset.${type.external_id}` : null;

/** First human message of a DRF error body ({field: [msg]} or {error: msg}). */
export function firstErrorMessage(err: unknown): string | null {
  if (!err || typeof err !== "object") return null;
  for (const value of Object.values(err as Record<string, unknown>)) {
    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return null;
}
```

- [ ] **Step 4: Chạy** — `pnpm --filter web test` → PASS. Nếu `toSorted` báo lỗi type (lib < ES2023), đổi thành `[...types].filter(...).sort(...)`.
- [ ] **Step 5:** `pnpm turbo run check:types --filter=web && pnpm turbo run check:lint --filter=web && pnpm fix:format`.
- [ ] **Step 6: Commit** — `feat(ee/web): work item type hierarchy rules`.

---

### Task 5: Service + store MobX + hooks

**Files:**
- Create: `apps/web/ee/work-item-types/service.ts`, `store.ts`, `hooks.ts`
- Modify: `apps/web/ee/work-item-types/work-item-types.test.ts` (thêm test store)

**Interfaces:**
- Consumes: `APIService` (`apps/web/services/api.service.ts`, methods `get/post/patch/delete(url, data?, config?)`), `API_BASE_URL` (`@plane/constants`), rules (Task 4).
- Produces:
  - `WorkItemTypeService`: `list(slug)`, `create(slug, data)`, `update(slug, id, data)`, `remove(slug, id, migrateTo?)`, `getProject(slug, pid)`, `setProcess(slug, pid, process)`, `assign(slug, pid, typeId)`, `unassign(slug, pid, typeId)`, `setDefault(slug, pid, typeId)`, `setEnabled(slug, pid, enabled)`.
  - `WorkItemTypeStore`: observable `projectMap`, `workspaceMap`; `getProject(pid)`, `getProjectTypes(pid)`, `resolveType(pid, typeId)`, `isEpic(pid, typeId)`, `getWorkspaceTypes(slug)`, `fetchProject`, `fetchWorkspace`, `createType`, `updateType`, `deleteType`, `setProcess`, `assign`, `unassign`, `setDefault`, `setEnabled`.
  - hooks: `useWorkItemTypes()`, `useProjectWorkItemTypes(slug, pid)`, `useWorkspaceWorkItemTypes(slug)`, `useParentIssueFilter(pid, typeId)`.

- [ ] **Step 1: Viết test fail** — nối vào cuối `work-item-types.test.ts`:

```ts
import { WorkItemTypeStore } from "./store";

describe("WorkItemTypeStore", () => {
  const payload = { process: "agile" as const, enabled: true, types: ALL };
  const fakeService = () => ({
    getProject: async () => payload,
    setProcess: async () => ({ process: "agile" }),
  });
  type TService = ConstructorParameters<typeof WorkItemTypeStore>[0];

  it("resolves null type_id to the project default and knows epics", async () => {
    const store = new WorkItemTypeStore(fakeService() as unknown as TService);
    await store.fetchProject("ws", "p1");
    expect(store.resolveType("p1", null)?.id).toBe("user_story");
    expect(store.resolveType("p1", "bug")?.id).toBe("bug");
    expect(store.isEpic("p1", "epic")).toBe(true);
    expect(store.isEpic("p1", "task")).toBe(false);
  });

  it("returns no types for a disabled or unknown project", async () => {
    const svc = { getProject: async () => ({ ...payload, enabled: false }) };
    const store = new WorkItemTypeStore(svc as unknown as TService);
    await store.fetchProject("ws", "p1");
    expect(store.getProjectTypes("p1")).toEqual([]);
    expect(store.getProjectTypes("nope")).toEqual([]);
    expect(store.resolveType("p1", null)).toBeUndefined();
  });

  it("refetches the project after changing its process", async () => {
    let calls = 0;
    const svc = { ...fakeService(), getProject: async () => (calls++, payload) };
    const store = new WorkItemTypeStore(svc as unknown as TService);
    await store.setProcess("ws", "p1", "agile");
    expect(calls).toBe(1);
    expect(store.getProject("p1")?.process).toBe("agile");
  });
});
```

- [ ] **Step 2:** `pnpm --filter web test` → FAIL `Cannot find module './store'`.

- [ ] **Step 3: Cài đặt** — `service.ts`:

```ts
import type { AxiosResponse } from "axios";
import { API_BASE_URL } from "@plane/constants";
import type { TIssueType, TProjectWorkItemTypes, TWorkItemProcess } from "@plane/types";
import { APIService } from "@/services/api.service";

// Errors are rethrown as the DRF body so callers can show it (same convention as the other web services).
const unwrap = <T>(request: Promise<AxiosResponse<T>>): Promise<T> =>
  request
    .then((res) => res?.data)
    .catch((err) => {
      throw err?.response?.data;
    });

export class WorkItemTypeService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private base = (slug: string) => `/api/workspaces/${slug}/work-item-types/`;
  private projectBase = (slug: string, projectId: string) =>
    `/api/workspaces/${slug}/projects/${projectId}/work-item-types/`;

  list = (slug: string): Promise<TIssueType[]> => unwrap(this.get(this.base(slug)));
  create = (slug: string, data: Partial<TIssueType>): Promise<TIssueType> => unwrap(this.post(this.base(slug), data));
  update = (slug: string, id: string, data: Partial<TIssueType>): Promise<TIssueType> =>
    unwrap(this.patch(`${this.base(slug)}${id}/`, data));
  remove = (slug: string, id: string, migrateTo?: string): Promise<void> =>
    unwrap(this.delete(`${this.base(slug)}${id}/`, undefined, { params: migrateTo ? { migrate_to: migrateTo } : {} }));

  getProject = (slug: string, projectId: string): Promise<TProjectWorkItemTypes> =>
    unwrap(this.get(this.projectBase(slug, projectId)));
  setProcess = (slug: string, projectId: string, process: TWorkItemProcess): Promise<{ process: TWorkItemProcess }> =>
    unwrap(this.post(this.projectBase(slug, projectId), { process }));
  assign = (slug: string, projectId: string, typeId: string): Promise<{ type_id: string }> =>
    unwrap(this.post(`${this.projectBase(slug, projectId)}assign/`, { type_id: typeId }));
  unassign = (slug: string, projectId: string, typeId: string): Promise<void> =>
    unwrap(this.delete(`${this.projectBase(slug, projectId)}assign/${typeId}/`));
  setDefault = (slug: string, projectId: string, typeId: string): Promise<void> =>
    unwrap(this.post(`${this.projectBase(slug, projectId)}default/`, { type_id: typeId }));
  /** Uses the existing project PATCH (spec: enable/disable has no dedicated endpoint). */
  setEnabled = (slug: string, projectId: string, enabled: boolean): Promise<unknown> =>
    unwrap(this.patch(`/api/workspaces/${slug}/projects/${projectId}/`, { is_issue_type_enabled: enabled }));
}
```

`store.ts`:

```ts
import { action, makeObservable, observable, runInAction } from "mobx";
import type { TIssueType, TProjectIssueType, TProjectWorkItemTypes, TWorkItemProcess } from "@plane/types";
import { defaultTypeId } from "./rules";
import type { WorkItemTypeService } from "./service";

const EMPTY: TProjectIssueType[] = [];

export class WorkItemTypeStore {
  projectMap: Record<string, TProjectWorkItemTypes> = {};
  workspaceMap: Record<string, TIssueType[]> = {};

  constructor(private service: WorkItemTypeService) {
    makeObservable(this, {
      projectMap: observable,
      workspaceMap: observable,
      setProject: action,
      setWorkspace: action,
    });
  }

  setProject = (projectId: string, data: TProjectWorkItemTypes) => {
    this.projectMap[projectId] = data;
  };
  setWorkspace = (slug: string, types: TIssueType[]) => {
    this.workspaceMap[slug] = types;
  };

  // getters
  getProject = (projectId: string | null | undefined) => (projectId ? this.projectMap[projectId] : undefined);
  /** Types usable in this project; empty when the feature is off or not loaded (callers then hide their UI). */
  getProjectTypes = (projectId: string | null | undefined): TProjectIssueType[] => {
    const config = this.getProject(projectId);
    return config?.enabled ? config.types : EMPTY;
  };
  /** `type_id = null` on legacy issues means the project default. */
  resolveType = (projectId: string | null | undefined, typeId: string | null | undefined) => {
    const types = this.getProjectTypes(projectId);
    const id = typeId ?? defaultTypeId(types);
    return types.find((type) => type.id === id);
  };
  isEpic = (projectId: string | null | undefined, typeId: string | null | undefined) =>
    !!this.resolveType(projectId, typeId)?.is_epic;
  getWorkspaceTypes = (slug: string | null | undefined) => (slug ? this.workspaceMap[slug] : undefined);

  // fetch
  fetchProject = async (slug: string, projectId: string) => {
    const data = await this.service.getProject(slug, projectId);
    this.setProject(projectId, data);
    return data;
  };
  fetchWorkspace = async (slug: string) => {
    const types = await this.service.list(slug);
    this.setWorkspace(slug, types);
    return types;
  };

  // workspace CRUD (workspace admin)
  createType = async (slug: string, data: Partial<TIssueType>) => {
    const created = await this.service.create(slug, data);
    runInAction(() => {
      this.workspaceMap[slug] = [...(this.workspaceMap[slug] ?? []), created];
    });
    return created;
  };
  updateType = async (slug: string, id: string, data: Partial<TIssueType>) => {
    const updated = await this.service.update(slug, id, data);
    runInAction(() => {
      this.workspaceMap[slug] = (this.workspaceMap[slug] ?? []).map((type) => (type.id === id ? updated : type));
    });
    return updated;
  };
  deleteType = async (slug: string, id: string, migrateTo?: string) => {
    await this.service.remove(slug, id, migrateTo);
    await this.fetchWorkspace(slug);
  };

  // project (project admin) — always refetch: the server owns process/default/enabled derivation
  setProcess = async (slug: string, projectId: string, process: TWorkItemProcess) => {
    await this.service.setProcess(slug, projectId, process);
    return this.fetchProject(slug, projectId);
  };
  assign = async (slug: string, projectId: string, typeId: string) => {
    await this.service.assign(slug, projectId, typeId);
    return this.fetchProject(slug, projectId);
  };
  unassign = async (slug: string, projectId: string, typeId: string) => {
    await this.service.unassign(slug, projectId, typeId);
    return this.fetchProject(slug, projectId);
  };
  setDefault = async (slug: string, projectId: string, typeId: string) => {
    await this.service.setDefault(slug, projectId, typeId);
    return this.fetchProject(slug, projectId);
  };
  setEnabled = async (slug: string, projectId: string, enabled: boolean) => {
    await this.service.setEnabled(slug, projectId, enabled);
    return this.fetchProject(slug, projectId);
  };
}
```

`hooks.ts`:

```ts
import useSWR from "swr";
import type { ISearchIssueResponse } from "@plane/types";
import { hierarchyReason } from "./rules";
import { WorkItemTypeService } from "./service";
import { WorkItemTypeStore } from "./store";

// ponytail: module singleton instead of a root-store slot (no core edit); data is keyed by slug/project id so it
// does not leak across workspaces. Add a reset on sign-out if stale types after switching accounts become a problem.
const store = new WorkItemTypeStore(new WorkItemTypeService());
const SWR_OPTIONS = { revalidateOnFocus: false, shouldRetryOnError: false } as const;

export const useWorkItemTypes = () => store;

/** Loads once per project (SWR dedupes the many badges of a list). Call from an observer component. */
export function useProjectWorkItemTypes(workspaceSlug: string | undefined, projectId: string | null | undefined) {
  useSWR(
    workspaceSlug && projectId ? ["WORK_ITEM_TYPES_PROJECT", workspaceSlug, projectId] : null,
    ([, slug, pid]: [string, string, string]) => store.fetchProject(slug, pid),
    SWR_OPTIONS
  );
  return store.getProject(projectId);
}

export function useWorkspaceWorkItemTypes(workspaceSlug: string | undefined) {
  useSWR(
    workspaceSlug ? ["WORK_ITEM_TYPES_WORKSPACE", workspaceSlug] : null,
    ([, slug]: [string, string]) => store.fetchWorkspace(slug),
    SWR_OPTIONS
  );
  return store.getWorkspaceTypes(workspaceSlug);
}

/** Parent picker filter: keep only issues whose type may parent the chosen type. undefined = no filtering. */
export function useParentIssueFilter(projectId: string | null | undefined, typeId: string | null | undefined) {
  const child = store.resolveType(projectId, typeId);
  if (!child) return undefined;
  return (issue: ISearchIssueResponse) => {
    const parent = store.resolveType(projectId, issue.type_id);
    return !parent || hierarchyReason(child, parent) === null;
  };
}
```

- [ ] **Step 4:** `pnpm --filter web test` → PASS (store chỉ `import type` service nên test không kéo axios/`@/`).
- [ ] **Step 5:** check types/lint/format như Global Constraints. Nếu `ISearchIssueResponse.type_id` không tồn tại trong `packages/types/src/search.ts`, dùng `(issue as { type_id?: string | null }).type_id` — `apps/api/plane/app/views/search/base.py:418` đã trả `type_id`.
- [ ] **Step 6: Commit** — `feat(ee/web): work item type service, store and hooks`.

---

### Task 6: i18n `en` + `vi-VN`

Đọc skill `.claude/skills/translate/SKILL.md` trước khi sửa. Placeholder ICU đơn ngoặc `{name}`; plural `{count, plural, one {...} other {...}}` (vi-VN vẫn phát cả `one` và `other` theo quy ước dự án). "Epic" giữ nguyên ở vi-VN (glossary). Khi thiếu key ở locale đang dùng, i18next rơi về `en` (`packages/i18n/src/core/instance.ts`: `fallbackLng: FALLBACK_LANGUAGE = "en"`, `fallbackNS` dò mọi namespace) — nhưng `pnpm --filter @plane/i18n check:sync` (CI) **fail khi locale khác thiếu key**, nên Task 13 bổ sung các locale còn lại.

**Files:**
- Modify: `packages/i18n/src/locales/en/work-item-type.json`, `packages/i18n/src/locales/vi-VN/work-item-type.json`, `deployments/ee/core-allowlist.txt`

- [ ] **Step 1:** Trong `en/work-item-type.json`, thêm key `"ee"` vào **trong** object `"work_item_types"` (cạnh `"label"`, `"settings"`…):

```json
"ee": {
  "field_label": "Work item type",
  "placeholder": "Type",
  "disabled_suffix": "Disabled",
  "filter_label": "Type",
  "change_failed": "Couldn't change the work item type. The previous type was kept.",
  "preset": {
    "epic": "Epic",
    "feature": "Feature",
    "bug": "Bug",
    "task": "Task",
    "sub_task": "Sub-task",
    "product_backlog_item": "Product Backlog Item",
    "user_story": "User Story"
  },
  "reason": {
    "needs_parent": "A sub-task needs a parent.",
    "epic_no_parent": "An epic can't have a parent.",
    "parent_level": "Pick a type below the parent's level.",
    "subtask_parent": "A sub-task can only sit under a task, bug or story level item."
  },
  "workspace": {
    "description": "Types are shared by every project in this workspace. Projects pick the ones they use.",
    "empty_title": "No work item types yet",
    "empty_description": "Choose Scrum or Agile in a project's settings to add the preset types, or create your own type here.",
    "level": "Level",
    "level_hint": "0–9. A parent must have a higher level than its child; 0 is a sub-task.",
    "is_epic": "Epic (can't have a parent)",
    "icon": "Icon",
    "background": "Background",
    "preset_badge": "Preset",
    "low_contrast": "The icon colour has low contrast against its background.",
    "delete_title": "Delete {name}",
    "delete_description": "This can't be undone.",
    "delete_in_use": "{count, plural, one {# work item uses} other {# work items use}} this type. Move them to:",
    "migrate_placeholder": "Pick a type",
    "delete_failed": "Couldn't delete the work item type.",
    "save_failed": "Couldn't save the work item type."
  },
  "project": {
    "description": "Choose a process and the types work items in this project can use.",
    "process": "Process",
    "scrum": "Scrum",
    "agile": "Agile",
    "custom": "Custom",
    "enabled": "Use work item types in this project",
    "assigned": "Used in this project",
    "available": "Other workspace types",
    "assign": "Add",
    "unassign": "Remove",
    "default_badge": "Default",
    "action_failed": "Couldn't update the project's work item types."
  }
}
```

- [ ] **Step 2:** `vi-VN/work-item-type.json`, cùng vị trí:

```json
"ee": {
  "field_label": "Loại mục công việc",
  "placeholder": "Loại",
  "disabled_suffix": "Đã tắt",
  "filter_label": "Loại",
  "change_failed": "Không đổi được loại mục công việc. Đã giữ loại cũ.",
  "preset": {
    "epic": "Epic",
    "feature": "Tính năng",
    "bug": "Lỗi",
    "task": "Nhiệm vụ",
    "sub_task": "Nhiệm vụ con",
    "product_backlog_item": "Mục Product Backlog",
    "user_story": "User Story"
  },
  "reason": {
    "needs_parent": "Nhiệm vụ con cần có mục cha.",
    "epic_no_parent": "Epic không được có mục cha.",
    "parent_level": "Hãy chọn loại có cấp thấp hơn mục cha.",
    "subtask_parent": "Nhiệm vụ con chỉ nằm dưới mục cấp nhiệm vụ, lỗi hoặc story."
  },
  "workspace": {
    "description": "Các loại dùng chung cho mọi dự án trong không gian làm việc. Mỗi dự án chọn loại mình dùng.",
    "empty_title": "Chưa có loại mục công việc",
    "empty_description": "Chọn Scrum hoặc Agile trong cài đặt dự án để thêm các loại có sẵn, hoặc tự tạo loại tại đây.",
    "level": "Cấp",
    "level_hint": "0–9. Mục cha phải có cấp cao hơn mục con; 0 là nhiệm vụ con.",
    "is_epic": "Epic (không được có mục cha)",
    "icon": "Biểu tượng",
    "background": "Nền",
    "preset_badge": "Có sẵn",
    "low_contrast": "Màu biểu tượng có độ tương phản thấp so với nền.",
    "delete_title": "Xoá {name}",
    "delete_description": "Không thể hoàn tác thao tác này.",
    "delete_in_use": "{count, plural, one {# mục công việc đang dùng} other {# mục công việc đang dùng}} loại này. Chuyển chúng sang:",
    "migrate_placeholder": "Chọn một loại",
    "delete_failed": "Không xoá được loại mục công việc.",
    "save_failed": "Không lưu được loại mục công việc."
  },
  "project": {
    "description": "Chọn quy trình và các loại mà mục công việc trong dự án này được dùng.",
    "process": "Quy trình",
    "scrum": "Scrum",
    "agile": "Agile",
    "custom": "Tuỳ chỉnh",
    "enabled": "Dùng loại mục công việc trong dự án này",
    "assigned": "Đang dùng trong dự án",
    "available": "Các loại khác của không gian làm việc",
    "assign": "Thêm",
    "unassign": "Gỡ",
    "default_badge": "Mặc định",
    "action_failed": "Không cập nhật được loại mục công việc của dự án."
  }
}
```

- [ ] **Step 3:** allowlist thêm `packages/i18n/src/locales/*/work-item-type.json` (glob — Task 13 sửa các locale khác).
- [ ] **Step 4:** `pnpm --filter @plane/i18n check:types` → PASS. `pnpm --filter @plane/i18n check:sync` sẽ báo các locale khác thiếu `work_item_types.ee.*` (không collision, không path conflict) — đúng mong đợi tới Task 13.
- [ ] **Step 5: Commit** — `feat(i18n): work item type strings (en, vi-VN)`.

---

### Task 7: Component `IssueTypeBadge`, `IssueTypeSelect`, `IssueTypeFormField`, `IssueTypeChange`

**Files:**
- Create: `apps/web/ee/work-item-types/components/type-name.ts`, `issue-type-badge.tsx`, `issue-type-select.tsx`, `issue-type-form-field.tsx`, `issue-type-change.tsx`

**Interfaces:**
- Consumes: hooks/store (Task 5), rules (Task 4), i18n (Task 6), `useIssueDetail` (`@/hooks/store/use-issue-detail`; `updateIssue(slug, pid, issueId, data)` ở root, `issue.getIssueById`).
- Produces:
  - `<IssueTypeBadge projectId typeId size? />`
  - `<IssueTypeSelect workspaceSlug projectId value mode hasParent parentTypeId onChange disabled? tabIndex? />` với `mode: "create" | "edit"`, `onChange(typeId, { auto })`
  - `<IssueTypeFormField workspaceSlug projectId hasParent parentTypeId onUserChange tabIndex? />` (dùng `useFormContext<TIssue>()`)
  - `<IssueTypeChange issueId disabled />`

- [ ] **Step 1:** `components/type-name.ts`:

```ts
import { useTranslation } from "@plane/i18n";
import type { TIssueType } from "@plane/types";
import { presetLabelKey } from "../rules";

/** Presets are translated by external_id; custom types show their name verbatim. */
export function useTypeName() {
  const { t } = useTranslation();
  return (type: Pick<TIssueType, "name" | "is_preset" | "external_id" | "is_active">) => {
    const key = presetLabelKey(type);
    const name = key ? t(key) : type.name;
    return type.is_active ? name : `${name} (${t("work_item_types.ee.disabled_suffix")})`;
  };
}
```

- [ ] **Step 2:** `components/issue-type-badge.tsx`:

```tsx
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useProjectWorkItemTypes, useWorkItemTypes } from "../hooks";
import { useTypeName } from "./type-name";

type Props = { projectId: string; typeId: string | null | undefined; size?: number };

export const IssueTypeBadge = observer(function IssueTypeBadge({ projectId, typeId, size = 14 }: Props) {
  const { workspaceSlug } = useParams();
  useProjectWorkItemTypes(workspaceSlug?.toString(), projectId);
  const store = useWorkItemTypes();
  const typeName = useTypeName();
  const type = store.resolveType(projectId, typeId);
  if (!type) return null;
  const label = typeName(type);
  return (
    <Tooltip label={label}>
      {/* the name is in aria-label + tooltip, never colour alone */}
      <span role="img" aria-label={label} className="inline-flex shrink-0 items-center">
        <Logo logo={type.logo_props} size={size} type="lucide" />
      </span>
    </Tooltip>
  );
});
```

- [ ] **Step 3:** `components/issue-type-select.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { observer } from "mobx-react";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { Pill as PillChrome } from "@makeplane/propel/elements/pill";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useTranslation } from "@plane/i18n";
import { useProjectWorkItemTypes, useWorkItemTypes } from "../hooks";
import { initialTypeId, suggestedChildTypeId, typeOptionsForParent, writeLastTypeId } from "../rules";
import { useTypeName } from "./type-name";

export type TIssueTypeSelectProps = {
  workspaceSlug: string;
  projectId: string | null;
  value: string | null | undefined;
  /** create: pre-fill (last used / default) and follow the parent; edit: never change the value by itself. */
  mode: "create" | "edit";
  hasParent: boolean;
  /** Parent's type_id; null = legacy parent (treated as project default); ignored when hasParent is false. */
  parentTypeId: string | null | undefined;
  onChange: (typeId: string, meta: { auto: boolean }) => void;
  disabled?: boolean;
  tabIndex?: number;
};

export const IssueTypeSelect = observer(function IssueTypeSelect(props: TIssueTypeSelectProps) {
  const { workspaceSlug, projectId, value, mode, hasParent, parentTypeId, onChange, disabled, tabIndex } = props;
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  useProjectWorkItemTypes(workspaceSlug, projectId);
  const types = store.getProjectTypes(projectId);
  // null = no parent; undefined = parent's type unknown → nothing muted (resolveType(undefined) would give the default)
  const parentType = !hasParent
    ? null
    : parentTypeId === undefined
      ? undefined
      : store.resolveType(projectId, parentTypeId);
  const pickedByUser = useRef(false);

  // create: fill an empty/stale value once types arrive (the provider seam covers the already-loaded case)
  useEffect(() => {
    if (mode !== "create" || !projectId || !types.length) return;
    if (value && types.some((type) => type.id === value)) return;
    const id = initialTypeId(types, projectId);
    if (id) onChange(id, { auto: true });
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [mode, projectId, types]);

  // create: quick sub-issue → level right below the parent, until the user picks something
  useEffect(() => {
    if (mode !== "create" || pickedByUser.current || !parentType) return;
    const id = suggestedChildTypeId(types, parentType);
    if (id && id !== value) onChange(id, { auto: true });
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [mode, parentType?.id, types]);

  if (!projectId || !types.length) return null; // feature off / load failed → no select, creation not blocked

  const current = store.resolveType(projectId, value);
  const options = typeOptionsForParent(types, parentType);

  return (
    <Menu>
      <MenuTrigger
        disabled={disabled}
        tabIndex={tabIndex}
        aria-label={`${t("work_item_types.ee.field_label")}: ${current ? typeName(current) : t("work_item_types.ee.placeholder")}`}
        render={
          <PillChrome size="sm" variant="outline">
            {current && <Logo logo={current.logo_props} size={14} type="lucide" />}
            <span>{current ? typeName(current) : t("work_item_types.ee.placeholder")}</span>
          </PillChrome>
        }
      />
      <MenuContent side="bottom" align="start">
        {options.map(({ type, reason }) => (
          <MenuItem
            key={type.id}
            label={typeName(type)}
            // muted with the reason shown, so it is readable without hovering
            description={reason ? t(`work_item_types.ee.reason.${reason}`) : undefined}
            icon={<Logo logo={type.logo_props} size={14} type="lucide" />}
            disabled={!!reason}
            onClick={() => {
              pickedByUser.current = true;
              writeLastTypeId(projectId, type.id);
              onChange(type.id, { auto: false });
            }}
          />
        ))}
      </MenuContent>
    </Menu>
  );
});
```

- [ ] **Step 4:** `components/issue-type-form-field.tsx`:

```tsx
import { observer } from "mobx-react";
import { useFormContext, useWatch } from "react-hook-form";
import type { TIssue } from "@plane/types";
import { IssueTypeSelect } from "./issue-type-select";

type Props = {
  workspaceSlug: string;
  projectId: string | null;
  hasParent: boolean;
  parentTypeId: string | null | undefined;
  onUserChange: () => void;
  tabIndex?: number;
};

/** Lives inside issue-modal/form.tsx's FormProvider. Auto picks do not dirty the form (no discard prompt). */
export const IssueTypeFormField = observer(function IssueTypeFormField(props: Props) {
  const { onUserChange, ...rest } = props;
  const { control, setValue } = useFormContext<TIssue>();
  const value = useWatch({ control, name: "type_id" });
  return (
    <IssueTypeSelect
      {...rest}
      mode="create"
      value={value}
      onChange={(typeId, { auto }) => {
        setValue("type_id", typeId, { shouldDirty: !auto, shouldValidate: true });
        if (!auto) onUserChange();
      }}
    />
  );
});
```

- [ ] **Step 5:** `components/issue-type-change.tsx`:

```tsx
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { firstErrorMessage } from "../rules";
import { IssueTypeSelect } from "./issue-type-select";

type Props = { issueId: string; disabled: boolean };

/** Change type of an existing work item through the normal issue PATCH (server validates parent/children). */
export const IssueTypeChange = observer(function IssueTypeChange({ issueId, disabled }: Props) {
  const { workspaceSlug } = useParams();
  const { t } = useTranslation();
  const {
    issue: { getIssueById },
    updateIssue,
  } = useIssueDetail();
  const issue = getIssueById(issueId);
  const parent = issue?.parent_id ? getIssueById(issue.parent_id) : undefined;
  if (!workspaceSlug || !issue?.project_id) return null;
  const projectId = issue.project_id;

  return (
    <IssueTypeSelect
      workspaceSlug={workspaceSlug.toString()}
      projectId={projectId}
      value={issue.type_id}
      mode="edit"
      hasParent={!!issue.parent_id}
      // parent not in the store → undefined parent type → nothing muted, the server still validates
      parentTypeId={parent ? parent.type_id : undefined}
      disabled={disabled}
      onChange={async (typeId) => {
        if (typeId === issue.type_id) return;
        try {
          await updateIssue(workspaceSlug.toString(), projectId, issueId, { type_id: typeId });
        } catch (error) {
          setToast({
            type: "error",
            title: t("work_item_types.update.toast.error.title"),
            message: firstErrorMessage(error) ?? t("work_item_types.ee.change_failed"),
          });
        }
      }}
    />
  );
});
```

- [ ] **Step 6: Xác minh giả định (trước khi chạy check)** — mở `@makeplane/propel` trong `node_modules/@makeplane/propel/dist/components/menu` (sau `pnpm install`): xác nhận `MenuTrigger` nhận `disabled`, `tabIndex`, `aria-label` (Base UI trigger truyền prop HTML xuống phần tử `render`), `MenuItem` nhận `description`, `icon`, `disabled` (đã thấy dùng ở `apps/web/components/comments/quick-actions.tsx:109`). Nếu `MenuTrigger` không có `disabled`, bỏ prop đó và bọc: `if (disabled) return <span className="inline-flex items-center gap-1">{badge + tên}</span>` trước `return <Menu>`.
  Xác nhận `projectIssues.updateIssue` hoàn tác optimistic update khi lỗi (đọc `updateIssue` trong `apps/web/store/issue/helpers/base-issues.store.ts`). Nếu **không** hoàn tác: trong `catch` của Step 5, sau `setToast`, thêm `await fetchIssue(workspaceSlug.toString(), projectId, issueId);` với `fetchIssue` destructure từ `useIssueDetail()` (kiểm tra tên/chữ ký trong `apps/web/store/issue/issue-details/root.store.ts`) để nạp lại giá trị server; không gửi PATCH hoàn tác.
- [ ] **Step 7:** `pnpm turbo run check:types --filter=web && pnpm turbo run check:lint --filter=web && pnpm fix:format` → PASS.
- [ ] **Step 8: Commit** — `feat(ee/web): issue type select, badge and change control`.

---

### Task 8: Seam modal tạo work item (provider, default-properties, parent picker)

**Files:**
- Modify: `apps/web/components/issues/issue-modal/provider.tsx`, `apps/web/components/issues/issue-modal/components/default-properties.tsx`, `apps/web/components/issues/parent-issues-list-modal.tsx`, `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Consumes: `IssueTypeFormField`, `useParentIssueFilter`, `useWorkItemTypes`, `initialTypeId`.
- Produces: `ParentIssuesListModal` nhận prop tuỳ chọn `filterIssue?: (issue: ISearchIssueResponse) => boolean`.

- [ ] **Step 1: `provider.tsx`** — thêm import và thay stub:

```tsx
// plugin
import { useWorkItemTypes } from "@/ee/work-item-types/hooks";
import { initialTypeId } from "@/ee/work-item-types/rules";
```
trong component, sau `const { projectsWithCreatePermissions } = useUser();`:
```tsx
  const workItemTypes = useWorkItemTypes();
```
và thay `getIssueTypeIdOnProjectChange: () => null,` bằng:
```tsx
        getIssueTypeIdOnProjectChange: (projectId: string) =>
          initialTypeId(workItemTypes.getProjectTypes(projectId), projectId),
```

- [ ] **Step 2: `default-properties.tsx`**:
  - import: thêm `useWatch` vào import `react-hook-form` (`import { Controller, useWatch } from "react-hook-form";`), và
    ```tsx
    // plugin
    import { IssueTypeFormField } from "@/ee/work-item-types/components/issue-type-form-field";
    import { useParentIssueFilter } from "@/ee/work-item-types/hooks";
    ```
  - sau `const projectDetails = getProjectById(projectId);`:
    ```tsx
    const typeId = useWatch({ control, name: "type_id" });
    const parentIssueFilter = useParentIssueFilter(projectId, typeId);
    ```
  - phần tử đầu tiên trong `<div className="flex flex-wrap items-center gap-2">`:
    ```tsx
    <IssueTypeFormField
      workspaceSlug={workspaceSlug}
      projectId={projectId}
      hasParent={!!parentId}
      parentTypeId={selectedParentIssue ? selectedParentIssue.type_id : undefined}
      onUserChange={handleFormChange}
    />
    ```
  - trong `<ParentIssuesListModal ... />` thêm `filterIssue={parentIssueFilter}`.
- [ ] **Step 3: `parent-issues-list-modal.tsx`** — `Props` thêm `filterIssue?: (issue: ISearchIssueResponse) => boolean;`, destructure `filterIssue` trong tham số hàm, và đổi `.then((res) => setIssues(res))` thành `.then((res) => setIssues(filterIssue ? res.filter(filterIssue) : res))`. Không thêm `filterIssue` vào deps của `useEffect` (hàm mới mỗi render sẽ gây gọi lại search) — thêm comment `// filterIssue is read at fetch time on purpose`.
- [ ] **Step 4:** allowlist thêm:
  ```
  apps/web/components/issues/issue-modal/provider.tsx
  apps/web/components/issues/issue-modal/components/default-properties.tsx
  apps/web/components/issues/parent-issues-list-modal.tsx
  ```
- [ ] **Step 5: Xác minh giả định** — `convertWorkItemDataToSearchResponse` (`packages/utils/src/work-item/modal.ts:22`) phải chép `type_id` sang response để parent preload (sub-issue nhanh) có type; nếu không chép, `selectedParentIssue.type_id` là `undefined` → không gợi ý. Khi đó **không** sửa utils; thay `parentTypeId` ở Step 2 bằng `selectedParentIssue ? (selectedParentIssue.type_id ?? getIssueById(selectedParentIssue.id)?.type_id) : undefined` với `const { issue: { getIssueById } } = useIssueDetail();` (import `useIssueDetail` từ `@/hooks/store/use-issue-detail`).
- [ ] **Step 6:** check types/lint/format → PASS; `pnpm --filter web test` vẫn PASS.
- [ ] **Step 7: Commit** — `feat(ee/web): pick work item type when creating work items`.

---

### Task 9: Seam hiển thị (badge trong `IssueIdentifier`, đổi type trong switcher)

Một seam ở `IssueIdentifier` phủ list (`issue-layouts/list/block.tsx:235`), kanban (`kanban/block.tsx:102`), spreadsheet (`spreadsheet/issue-row.tsx:291`), calendar, gantt, sub-issues, parent, relations, peek (qua `IssueTypeSwitcher` ở `peek-overview/issue-detail.tsx:95`) — **không** sửa từng block.

**Files:**
- Modify: `apps/web/components/issues/issue-detail/issue-identifier.tsx`, `apps/web/components/issues/issue-type-switcher.tsx`, `deployments/ee/core-allowlist.txt`

- [ ] **Step 1: `issue-identifier.tsx`** — import `import { IssueTypeBadge } from "@/ee/work-item-types/components/issue-type-badge";`; sau `const issueSequenceId = ...` thêm
  ```tsx
  const issueTypeId = isUsingStoreData ? issue?.type_id : props.issueTypeId;
  ```
  và trong `<div className="flex shrink-0 items-center space-x-2">` đặt trước `<IdentifierText`:
  ```tsx
  <IssueTypeBadge projectId={projectId} typeId={issueTypeId} />
  ```
- [ ] **Step 2: `issue-type-switcher.tsx`** — import `import { IssueTypeChange } from "@/ee/work-item-types/components/issue-type-change";`, lấy `disabled` từ props (`const { issueId, disabled } = props;`) và thay `return <IssueIdentifier ... />;` bằng:
  ```tsx
  return (
    <div className="flex items-center gap-2">
      <IssueIdentifier issueId={issueId} projectId={issue.project_id} size="md" enableClickToCopyIdentifier />
      <IssueTypeChange issueId={issueId} disabled={disabled} />
    </div>
  );
  ```
- [ ] **Step 3:** allowlist thêm `apps/web/components/issues/issue-detail/issue-identifier.tsx`, `apps/web/components/issues/issue-type-switcher.tsx`.
- [ ] **Step 4: Xác minh Epic không đi luồng EPICS** — `grep -rn "is_epic" apps/web --include=*.tsx --include=*.ts | grep -v "/ee/"` : mọi nhánh `issue.is_epic` (ví dụ `apps/web/app/(all)/[workspaceSlug]/(projects)/browse/[workItem]/page.tsx:71`) đọc field mà API không trả → `undefined` → luồng ISSUES. Và `grep -rn "/epics/" apps/web/services apps/web/store` : chỉ được gọi khi `serviceType === EPICS` (không ai tạo được trạng thái đó vì `is_epic` luôn undefined). Ghi kết quả grep vào mô tả commit; nếu có đường gọi `/epics/` vô điều kiện, dừng và báo người duyệt (không tự thêm route).
- [ ] **Step 5:** check types/lint/format → PASS.
- [ ] **Step 6: Commit** — `feat(ee/web): show work item type badge and change type in detail/peek`.

---

### Task 10: Rich filter `Type`

**Files:**
- Create: `apps/web/ee/work-item-types/filter-config.tsx`
- Modify: `packages/types/src/view-props.ts` (thêm `"type_id"` vào `WORK_ITEM_FILTER_PROPERTY_KEYS`), `packages/constants/src/issue/filter.ts` (thêm vào `ISSUE_DISPLAY_FILTERS_BY_PAGE.issues.filters`), `apps/web/hooks/work-item-filters/use-work-item-filters-config.tsx`, `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Consumes: `createFilterConfig`, `createOperatorConfigEntry`, `getMultiSelectConfig`, types `TCreateFilterConfigParams`, `IFilterIconConfig` (`@plane/utils` rich-filters, cùng mẫu `packages/utils/src/work-item-filters/configs/filters/label.ts`); backend `type_id`/`type_id__in` (Task 1).
- Produces: `useWorkItemTypeFilterConfig({ workspaceSlug, projectId, isEnabled, operatorConfigs }): TFilterConfig<TWorkItemFilterProperty>`.

Chỉ thêm ở trang `issues` (project/cycle/module/view): danh sách type theo project; trang workspace (`my_issues`, `profile_issues`) không có project cụ thể nên bỏ qua.

- [ ] **Step 1:** `view-props.ts` — thêm `"type_id",` sau `"project_id",` trong `WORK_ITEM_FILTER_PROPERTY_KEYS`. `filter.ts` — trong `issues: { filters: [...] }` thêm `"type_id",` sau `"label_id",`.
- [ ] **Step 2:** `apps/web/ee/work-item-types/filter-config.tsx`:

```tsx
import { useMemo } from "react";
import { WorkItemsOutline } from "@makeplane/propel/icons";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import type { TFilterConfig, TLogoProps, TProjectIssueType, TWorkItemFilterProperty } from "@plane/types";
import { COLLECTION_OPERATOR, EQUALITY_OPERATOR } from "@plane/types";
import type { TCreateFilterConfigParams } from "@plane/utils";
import { createFilterConfig, createOperatorConfigEntry, getMultiSelectConfig } from "@plane/utils";
import { useProjectWorkItemTypes, useWorkItemTypes } from "./hooks";
import { useTypeName } from "./components/type-name";

type TParams = {
  workspaceSlug: string;
  projectId: string | undefined;
  isEnabled: boolean;
  operatorConfigs: Omit<TCreateFilterConfigParams, "isEnabled">;
};

export function useWorkItemTypeFilterConfig(params: TParams): TFilterConfig<TWorkItemFilterProperty> {
  const { workspaceSlug, projectId, isEnabled, operatorConfigs } = params;
  useProjectWorkItemTypes(workspaceSlug, projectId);
  const types = useWorkItemTypes().getProjectTypes(projectId);
  const typeName = useTypeName();

  return useMemo(() => {
    const base = { isEnabled: isEnabled && types.length > 0, ...operatorConfigs };
    return createFilterConfig<TWorkItemFilterProperty>({
      id: "type_id",
      label: "Type",
      ...base,
      icon: WorkItemsOutline,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, base, (updatedParams) =>
          getMultiSelectConfig<TProjectIssueType, string, TLogoProps>(
            {
              items: types,
              getId: (type) => type.id,
              getLabel: (type) => typeName(type),
              getValue: (type) => type.id,
              getIconData: (type) => type.logo_props,
            },
            { singleValueOperator: EQUALITY_OPERATOR.EXACT, ...updatedParams },
            { getOptionIcon: (logo) => <Logo logo={logo} size={12} type="lucide" /> }
          )
        ),
      ]),
    });
  }, [isEnabled, operatorConfigs, types, typeName]);
}
```

  Ghi chú: `label: "Type"` theo đúng quy ước các config core (`"Priority"`, `"Label"` không dịch). `typeName` đổi tham chiếu mỗi render → memo chạy lại mỗi render; chấp nhận (danh sách ≤ 50).
- [ ] **Step 3:** `use-work-item-filters-config.tsx`:
  - import `import { useWorkItemTypeFilterConfig } from "@/ee/work-item-types/filter-config";`
  - sau khối `priorityFilterConfig`:
    ```tsx
    // work item type filter config (plugin)
    const typeFilterConfig = useWorkItemTypeFilterConfig({
      workspaceSlug,
      projectId,
      isEnabled: isFilterEnabled("type_id"),
      operatorConfigs,
    });
    ```
  - thêm `typeFilterConfig,` vào mảng `configs` (sau `priorityFilterConfig,`) và `type_id: typeFilterConfig,` vào `configMap`.
- [ ] **Step 4: Xác minh kiểu `operatorConfigs`** — mở `apps/web/hooks/rich-filters/use-filters-operator-configs.ts*`: nếu kiểu trả về không gán được cho `Omit<TCreateFilterConfigParams, "isEnabled">`, đổi kiểu field trong `TParams` thành `ReturnType<typeof useFiltersOperatorConfigs>` (import hook từ `@/hooks/rich-filters/use-filters-operator-configs`). Xác minh `TLogoProps` thoả `TFilterIconType` (object) — đã đúng theo `packages/utils/src/rich-filters/factories/configs/shared.ts`.
- [ ] **Step 5: Xác minh đường gửi filter** — rich filter gửi `{"type_id__in": "<a>,<b>"}` hoặc `{"type_id": "<a>"}` giống `label_id`; với Task 1 backend đã nhận. Chạy `grep -rn "label_id" packages/shared-state/src/store/work-item-filters/adapter.ts`: nếu adapter có map riêng cho từng property (ngoài `WORK_ITEM_FILTER_PROPERTY_KEYS.includes`), thêm `type_id` tương tự `label_id` và allowlist file đó.
- [ ] **Step 6:** allowlist thêm:
  ```
  packages/types/src/view-props.ts
  packages/constants/src/issue/filter.ts
  apps/web/hooks/work-item-filters/use-work-item-filters-config.tsx
  ```
- [ ] **Step 7:** `pnpm turbo run check:types --filter=web --filter=@plane/types --filter=@plane/constants --filter=@plane/shared-state`, lint, format → PASS.
- [ ] **Step 8: Commit** — `feat(ee/web): Type filter in work item rich filters`.

---

### Task 11: Workspace Settings — CRUD type

**Files:**
- Create: `apps/web/ee/work-item-types/components/type-form-dialog.tsx`, `type-delete-dialog.tsx`, `apps/web/ee/work-item-types/pages/workspace-settings.tsx`
- Modify: `apps/web/app/routes/extended.ts`, `packages/types/src/settings.ts`, `packages/constants/src/settings/workspace.ts`, `apps/web/components/settings/workspace/sidebar/item-icon.tsx`, `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Consumes: store (`fetchWorkspace/createType/updateType/deleteType`), `useWorkspaceWorkItemTypes`, `EmojiPicker` + `ChangeHandlerPayload` (`@plane/blocks/emoji-icon-picker`), Dialog/Button/Switch/InputField (propel), `useUserPermissions().allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE)`.
- Produces: route `/:workspaceSlug/settings/work-item-types`, tab key `"work-item-types"`.

- [ ] **Step 1: Đăng ký route** — `apps/web/app/routes/extended.ts` (giữ header):

```ts
import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

// Same layout chain as routes/core.ts so mergeRoutes() nests these under the existing settings layouts.
export const extendedRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(settings)/layout.tsx", [
        layout("./(all)/[workspaceSlug]/(settings)/settings/(workspace)/layout.tsx", [
          route(":workspaceSlug/settings/work-item-types", "../ee/work-item-types/pages/workspace-settings.tsx"),
        ]),
        layout("./(all)/[workspaceSlug]/(settings)/settings/projects/layout.tsx", [
          layout("./(all)/[workspaceSlug]/(settings)/settings/projects/[projectId]/layout.tsx", [
            route(
              ":workspaceSlug/settings/projects/:projectId/work-item-types",
              "../ee/work-item-types/pages/project-settings.tsx"
            ),
          ]),
        ]),
      ]),
    ]),
  ]),
];
```

  Tạo luôn `pages/project-settings.tsx` tạm với nội dung `export default function ProjectWorkItemTypesPage() { return null; }` (Task 12 thay) để route resolve.
  **Xác minh trước:** `pnpm --filter web exec react-router routes` phải in 2 route mới lồng dưới `(workspace)/layout.tsx` và `[projectId]/layout.tsx`. Nếu react-router từ chối file ngoài `app/` (`../ee/...`), tạo 2 file re-export `apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/work-item-types/page.tsx` và `.../projects/[projectId]/work-item-types/page.tsx` với nội dung `export { default } from "@/ee/work-item-types/pages/workspace-settings";` (tương ứng `project-settings`), đổi đường dẫn file trong `extended.ts` sang `./(all)/...`, và allowlist 2 file đó.
- [ ] **Step 2: Tab + sidebar**
  - `packages/types/src/settings.ts`: `TWorkspaceSettingsTabs` thêm `| "work-item-types"`.
  - `packages/constants/src/settings/workspace.ts`: thêm vào `WORKSPACE_SETTINGS` (sau `webhooks`):
    ```ts
    "work-item-types": {
      key: "work-item-types",
      i18n_label: "work_item_types.label",
      href: `/settings/work-item-types`,
      access: [EUserWorkspaceRoles.ADMIN],
      highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/work-item-types/`,
    },
    ```
    và `[WORKSPACE_SETTINGS_CATEGORY.FEATURES]: [WORKSPACE_SETTINGS["work-item-types"]],`.
  - `apps/web/components/settings/workspace/sidebar/item-icon.tsx`: thêm `WorkItemsOutline` vào import `@makeplane/propel/icons` và `"work-item-types": WorkItemsOutline,` vào map.
  - Xác minh: `WORKSPACE_SETTINGS_ACCESS` (`(workspace)/layout.tsx:37`) tự có key `/settings/work-item-types` → member bị `NotAuthorizedView`. Category `FEATURES` trước đây rỗng: mở `components/settings/workspace/sidebar/item-categories.tsx` xác nhận category rỗng/không rỗng đều render tiêu đề đúng (`common.features`).
- [ ] **Step 3:** `components/type-form-dialog.tsx`:

```tsx
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { Switch } from "@makeplane/propel/components/switch";
import { EmojiPicker, Logo } from "@plane/blocks/emoji-icon-picker";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TIssueType } from "@plane/types";
import { firstErrorMessage } from "../rules";

type TFormValues = Pick<TIssueType, "name" | "description" | "level" | "is_epic" | "logo_props">;

type Props = {
  isOpen: boolean;
  type?: TIssueType; // undefined = create
  onClose: () => void;
  onSubmit: (data: Partial<TIssueType>) => Promise<TIssueType>;
};

const NEW_TYPE: TFormValues = {
  name: "",
  description: "",
  level: 1,
  is_epic: false,
  logo_props: { in_use: "icon", icon: { name: "CheckSquare", color: "#3B82F6", background_color: "#FFFFFF" } },
};

export function TypeFormDialog({ isOpen, type, onClose, onSubmit }: Props) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);
  const {
    control,
    handleSubmit,
    register,
    watch,
    setValue,
    formState: { isSubmitting, errors },
  } = useForm<TFormValues>({ values: type ? { ...NEW_TYPE, ...type } : NEW_TYPE });
  const logo = watch("logo_props");
  const isPreset = !!type?.is_preset; // presets keep their level and epic flag (server enforces too)

  const submit = async (values: TFormValues) => {
    try {
      const saved = await onSubmit({ ...values, level: Number(values.level) });
      if (saved.low_contrast) {
        setToast({ type: "warning", title: saved.name, message: t("work_item_types.ee.workspace.low_contrast") });
      }
      onClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("work_item_types.create.toast.error.title"),
        message: firstErrorMessage(error) ?? t("work_item_types.ee.workspace.save_failed"),
      });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="md">
        <form onSubmit={handleSubmit(submit)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{type ? t("work_item_types.update.title") : t("work_item_types.create.title")}</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <EmojiPicker
                    isOpen={pickerOpen}
                    handleToggle={setPickerOpen}
                    iconType="lucide"
                    showEmojiTab={false}
                    defaultOpen="icon"
                    defaultIconColor={logo.icon?.color ?? "#6d7b8a"}
                    label={
                      <span
                        aria-label={t("work_item_types.ee.workspace.icon")}
                        className="flex size-9 items-center justify-center rounded-md border border-subtle"
                        style={{ backgroundColor: logo.icon?.background_color }}
                      >
                        <Logo logo={logo} size={18} type="lucide" />
                      </span>
                    }
                    onChange={(value) => {
                      if (value.type !== "icon") return;
                      setValue("logo_props", {
                        in_use: "icon",
                        icon: { ...logo.icon, name: value.value.name, color: value.value.color },
                      });
                    }}
                  />
                  <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
                    {t("work_item_types.ee.workspace.background")}
                    {/* native colour input: no picker dependency */}
                    <input
                      type="color"
                      value={logo.icon?.background_color ?? "#FFFFFF"}
                      onChange={(e) =>
                        setValue("logo_props", {
                          in_use: "icon",
                          icon: { ...logo.icon, background_color: e.target.value.toUpperCase() },
                        })
                      }
                    />
                  </label>
                </div>
                <Controller
                  control={control}
                  name="name"
                  rules={{ required: true, validate: (v) => v.trim().length > 0 }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="wit-name"
                      name="name"
                      value={value}
                      onChange={onChange}
                      ref={ref}
                      size="2xl"
                      orientation="vertical"
                      placeholder={t("work_item_types.create_update.form.name.placeholder")}
                      error={errors.name ? t("work_item_types.create_update.form.name.placeholder") : undefined}
                    />
                  )}
                />
                <textarea
                  {...register("description")}
                  rows={3}
                  className="w-full rounded-md border border-subtle bg-transparent px-3 py-2 text-body-xs-regular"
                  placeholder={t("work_item_types.create_update.form.description.placeholder")}
                />
                <Controller
                  control={control}
                  name="level"
                  rules={{ min: 0, max: 9, required: true }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="wit-level"
                      name="level"
                      type="number"
                      min={0}
                      max={9}
                      value={value?.toString()}
                      onChange={onChange}
                      ref={ref}
                      size="2xl"
                      orientation="vertical"
                      disabled={isPreset}
                      placeholder={t("work_item_types.ee.workspace.level")}
                      error={errors.level ? t("work_item_types.ee.workspace.level_hint") : undefined}
                    />
                  )}
                />
                <p className="text-body-xs-regular text-tertiary">{t("work_item_types.ee.workspace.level_hint")}</p>
                <Controller
                  control={control}
                  name="is_epic"
                  render={({ field: { value, onChange } }) => (
                    <label className="flex items-center gap-2 text-body-xs-regular">
                      <Switch size="sm" checked={value} disabled={isPreset} onCheckedChange={onChange} />
                      {t("work_item_types.ee.workspace.is_epic")}
                    </label>
                  )}
                />
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={onClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              label={type ? t("work_item_types.update.button") : t("work_item_types.create.button")}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

  Xác minh: key `cancel` tồn tại (`grep -rn '"cancel":' packages/i18n/src/locales/en/`), nếu không dùng `common.cancel`; `setToast` nhận `type: "warning"` (xem `packages/blocks/src/toast`), nếu không có dùng `"info"`; `Switch` nhận `disabled` (xem `apps/web/components/automation/auto-close-automation.tsx`). `InputField` khi `type="number"` trả chuỗi → `submit` ép `Number(...)`.
- [ ] **Step 4:** `components/type-delete-dialog.tsx`:

```tsx
import { useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TIssueType, TIssueTypeConflict } from "@plane/types";
import { firstErrorMessage } from "../rules";
import { useTypeName } from "./type-name";

type Props = {
  type: TIssueType | null;
  candidates: TIssueType[]; // other types the issues may move to
  onClose: () => void;
  onDelete: (migrateTo?: string) => Promise<void>;
};

export function TypeDeleteDialog({ type, candidates, onClose, onDelete }: Props) {
  const { t } = useTranslation();
  const typeName = useTypeName();
  const [inUse, setInUse] = useState<number | null>(null); // set after a 409 with a count
  const [migrateTo, setMigrateTo] = useState("");
  const [busy, setBusy] = useState(false);
  const close = () => {
    setInUse(null);
    setMigrateTo("");
    onClose();
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await onDelete(migrateTo || undefined);
      close();
    } catch (error) {
      const conflict = error as TIssueTypeConflict | undefined;
      if (typeof conflict?.count === "number" && conflict.count > 0 && !migrateTo) setInUse(conflict.count);
      else
        setToast({
          type: "error",
          title: t("work_item_types.settings.item_delete_confirmation.toast.error.title"),
          message: firstErrorMessage(error) ?? t("work_item_types.ee.workspace.delete_failed"),
        });
    } finally {
      setBusy(false);
    }
  };

  if (!type) return null;
  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent size="sm">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("work_item_types.ee.workspace.delete_title", { name: typeName(type) })}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <p className="text-body-xs-regular text-secondary">{t("work_item_types.ee.workspace.delete_description")}</p>
            {inUse !== null && (
              <label className="mt-3 flex flex-col gap-1 text-body-xs-regular">
                {t("work_item_types.ee.workspace.delete_in_use", { count: inUse })}
                <select
                  value={migrateTo}
                  onChange={(e) => setMigrateTo(e.target.value)}
                  className="rounded-md border border-subtle bg-transparent px-2 py-1"
                >
                  <option value="">{t("work_item_types.ee.workspace.migrate_placeholder")}</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {typeName(c)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={close} />
          <Button
            variant="error-fill"
            size="md"
            stretch="auto"
            loading={busy}
            disabled={inUse !== null && !migrateTo}
            label={t("work_item_types.settings.item_delete_confirmation.primary_button")}
            onClick={confirm}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
```

  Xác minh: tên variant nút xoá của propel — `grep -rn 'variant="error' apps/web/components | head -3`; dùng đúng tên đang có (vd `"error-fill"`/`"danger"`). Server trả 409 `{error,count}` khi còn issue dùng và không có `migrate_to`; khi `migrate_to` sai level server trả 400 → toast.
- [ ] **Step 5:** `pages/workspace-settings.tsx`:

```tsx
import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TIssueType } from "@plane/types";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useUserPermissions } from "@/hooks/store/user";
import { TypeDeleteDialog } from "../components/type-delete-dialog";
import { TypeFormDialog } from "../components/type-form-dialog";
import { useTypeName } from "../components/type-name";
import { useWorkItemTypes, useWorkspaceWorkItemTypes } from "../hooks";

function WorkspaceWorkItemTypesPage() {
  const { workspaceSlug: slugParam } = useParams();
  const workspaceSlug = slugParam?.toString() ?? "";
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const types = useWorkspaceWorkItemTypes(isAdmin ? workspaceSlug : undefined);
  const [editing, setEditing] = useState<TIssueType | "new" | null>(null);
  const [deleting, setDeleting] = useState<TIssueType | null>(null);

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" className="h-auto" />;

  const sorted = [...(types ?? [])].sort((a, b) => b.level - a.level || a.name.localeCompare(b.name));

  return (
    <SettingsContentWrapper>
      <PageHead title={t("work_item_types.label")} />
      <SettingsHeading
        title={t("work_item_types.label")}
        description={t("work_item_types.ee.workspace.description")}
        control={
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label={t("work_item_types.create.button")}
            onClick={() => setEditing("new")}
          />
        }
      />
      {types && sorted.length === 0 && (
        <div className="mt-6 rounded-md border border-subtle p-6">
          <p className="text-body-sm-medium">{t("work_item_types.ee.workspace.empty_title")}</p>
          <p className="text-body-xs-regular text-tertiary">{t("work_item_types.ee.workspace.empty_description")}</p>
        </div>
      )}
      <ul className="mt-6 flex flex-col divide-y divide-subtle">
        {sorted.map((type) => (
          <li key={type.id} className="flex items-center gap-3 py-3">
            <span
              className="flex size-7 items-center justify-center rounded-md"
              style={{ backgroundColor: type.logo_props.icon?.background_color }}
            >
              <Logo logo={type.logo_props} size={16} type="lucide" />
            </span>
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-body-sm-medium">{typeName(type)}</span>
              <span className="text-body-xs-regular text-tertiary">
                {t("work_item_types.ee.workspace.level")} {type.level}
                {type.is_preset && ` · ${t("work_item_types.ee.workspace.preset_badge")}`}
                {type.low_contrast && ` · ${t("work_item_types.ee.workspace.low_contrast")}`}
              </span>
            </div>
            <Button variant="secondary" size="sm" stretch="auto" label={t("edit")} onClick={() => setEditing(type)} />
            {!type.is_preset && (
              <Button variant="secondary" size="sm" stretch="auto" label={t("delete")} onClick={() => setDeleting(type)} />
            )}
          </li>
        ))}
      </ul>
      <TypeFormDialog
        isOpen={editing !== null}
        type={editing && editing !== "new" ? editing : undefined}
        onClose={() => setEditing(null)}
        onSubmit={(data) =>
          editing && editing !== "new"
            ? store.updateType(workspaceSlug, editing.id, data)
            : store.createType(workspaceSlug, data)
        }
      />
      <TypeDeleteDialog
        type={deleting}
        candidates={sorted.filter((c) => c.id !== deleting?.id && c.is_active && c.level === deleting?.level)}
        onClose={() => setDeleting(null)}
        onDelete={(migrateTo) => store.deleteType(workspaceSlug, deleting!.id, migrateTo)}
      />
    </SettingsContentWrapper>
  );
}

export default observer(WorkspaceWorkItemTypesPage);
```

  Ghi chú: candidates lọc **cùng level** (spec "cùng/tương thích level"; server là nguồn sự thật). Xác minh key `edit`/`delete` tồn tại trong `en/*.json` (`grep -rn '"edit":\|"delete":' packages/i18n/src/locales/en`), không thì dùng `common.edit`/`common.delete`; xác minh class `text-body-sm-medium` có trong design tokens (`grep -rn "text-body-sm-medium" apps/web/components | head -1`), không có thì dùng `text-body-xs-medium`.
- [ ] **Step 6:** allowlist thêm:
  ```
  apps/web/app/routes/extended.ts
  packages/types/src/settings.ts
  packages/constants/src/settings/workspace.ts
  apps/web/components/settings/workspace/sidebar/item-icon.tsx
  ```
- [ ] **Step 7:** `pnpm turbo run check:types --filter=web --filter=@plane/types --filter=@plane/constants`, lint, format → PASS.
- [ ] **Step 8: Commit** — `feat(ee/web): workspace settings page for work item types`.

---

### Task 12: Project Settings — process, gán type, default, bật/tắt

**Files:**
- Modify: `apps/web/ee/work-item-types/pages/project-settings.tsx` (thay bản tạm của Task 11), `packages/types/src/settings.ts`, `packages/constants/src/settings/project.ts`, `apps/web/components/settings/project/sidebar/item-icon.tsx`, `deployments/ee/core-allowlist.txt`

**Interfaces:**
- Consumes: store (`setProcess/assign/unassign/setDefault/setEnabled`), `useProjectWorkItemTypes`, `useWorkspaceWorkItemTypes`, `allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT)`.

- [ ] **Step 1: Tab + sidebar**
  - `settings.ts`: `TProjectSettingsTabs` thêm `| "work_item_types"`.
  - `project.ts`: thêm vào `PROJECT_SETTINGS` (sau `labels`):
    ```ts
    work_item_types: {
      key: "work_item_types",
      i18n_label: "work_item_types.label",
      href: `/work-item-types`,
      access: [EUserProjectRoles.ADMIN],
      highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/work-item-types/`,
    },
    ```
    và trong `GROUPED_PROJECT_SETTINGS[WORK_STRUCTURE]` thêm `PROJECT_SETTINGS["work_item_types"],` sau `PROJECT_SETTINGS["labels"],`.
  - `project/sidebar/item-icon.tsx`: import thêm `WorkItemsOutline` từ `@makeplane/propel/icons`, map `work_item_types: WorkItemsOutline,`.
- [ ] **Step 2:** `pages/project-settings.tsx`:

```tsx
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TWorkItemProcess } from "@plane/types";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useUserPermissions } from "@/hooks/store/user";
import { useTypeName } from "../components/type-name";
import { useProjectWorkItemTypes, useWorkItemTypes, useWorkspaceWorkItemTypes } from "../hooks";
import { firstErrorMessage } from "../rules";

const PROCESSES: TWorkItemProcess[] = ["scrum", "agile"];

function ProjectWorkItemTypesPage() {
  const params = useParams();
  const workspaceSlug = params.workspaceSlug?.toString() ?? "";
  const projectId = params.projectId?.toString() ?? "";
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const config = useProjectWorkItemTypes(isAdmin ? workspaceSlug : undefined, projectId);
  const workspaceTypes = useWorkspaceWorkItemTypes(isAdmin ? workspaceSlug : undefined);

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  // every action refetches the project; errors (409 in-use, 400 invalid) are shown verbatim from the server
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
    } catch (error) {
      setToast({
        type: "error",
        title: t("work_item_types.update.toast.error.title"),
        message: firstErrorMessage(error) ?? t("work_item_types.ee.project.action_failed"),
      });
    }
  };

  const assigned = config?.types ?? [];
  const assignedIds = new Set(assigned.map((type) => type.id));
  const available = (workspaceTypes ?? []).filter((type) => type.is_active && !assignedIds.has(type.id));

  return (
    <SettingsContentWrapper>
      <PageHead title={t("work_item_types.label")} />
      <SettingsHeading
        title={t("work_item_types.label")}
        description={t("work_item_types.ee.project.description")}
        control={
          config && (
            <label className="flex items-center gap-2 text-body-xs-regular">
              <Switch
                size="sm"
                checked={config.enabled}
                onCheckedChange={(enabled) => run(() => store.setEnabled(workspaceSlug, projectId, enabled))}
              />
              {t("work_item_types.ee.project.enabled")}
            </label>
          )
        }
      />
      <section className="mt-6 flex flex-col gap-2">
        <h4 className="text-body-sm-medium">{t("work_item_types.ee.project.process")}</h4>
        <div role="radiogroup" aria-label={t("work_item_types.ee.project.process")} className="flex gap-2">
          {PROCESSES.map((process) => (
            <Button
              key={process}
              role="radio"
              aria-checked={config?.process === process}
              variant={config?.process === process ? "primary" : "secondary"}
              size="md"
              stretch="auto"
              label={t(`work_item_types.ee.project.${process}`)}
              onClick={() => run(() => store.setProcess(workspaceSlug, projectId, process))}
            />
          ))}
          {config && config.enabled && config.process === null && (
            <span className="self-center text-body-xs-regular text-tertiary">
              {t("work_item_types.ee.project.custom")}
            </span>
          )}
        </div>
      </section>
      <section className="mt-6">
        <h4 className="text-body-sm-medium">{t("work_item_types.ee.project.assigned")}</h4>
        <ul className="mt-2 flex flex-col divide-y divide-subtle">
          {[...assigned]
            .sort((a, b) => b.level - a.level || a.name.localeCompare(b.name))
            .map((type) => (
              <li key={type.id} className="flex items-center gap-3 py-2">
                <Logo logo={type.logo_props} size={16} type="lucide" />
                <span className="flex-1 truncate text-body-xs-regular">{typeName(type)}</span>
                {type.is_project_default ? (
                  <span className="text-body-xs-regular text-tertiary">{t("work_item_types.ee.project.default_badge")}</span>
                ) : (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={t("work_item_types.settings.set_as_default")}
                      onClick={() => run(() => store.setDefault(workspaceSlug, projectId, type.id))}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={t("work_item_types.ee.project.unassign")}
                      onClick={() => run(() => store.unassign(workspaceSlug, projectId, type.id))}
                    />
                  </>
                )}
              </li>
            ))}
        </ul>
      </section>
      {available.length > 0 && (
        <section className="mt-6">
          <h4 className="text-body-sm-medium">{t("work_item_types.ee.project.available")}</h4>
          <ul className="mt-2 flex flex-col divide-y divide-subtle">
            {available.map((type) => (
              <li key={type.id} className="flex items-center gap-3 py-2">
                <Logo logo={type.logo_props} size={16} type="lucide" />
                <span className="flex-1 truncate text-body-xs-regular">{typeName(type)}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label={t("work_item_types.ee.project.assign")}
                  onClick={() => run(() => store.assign(workspaceSlug, projectId, type.id))}
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </SettingsContentWrapper>
  );
}

export default observer(ProjectWorkItemTypesPage);
```

- [ ] **Step 3: Xác minh giả định** — (a) `PATCH /api/workspaces/<slug>/projects/<pid>/` với `{"is_issue_type_enabled": false}` có được lưu không: mở `apps/api/plane/app/serializers/project.py` (`ProjectSerializer`), nếu field nằm trong `read_only_fields` hoặc bị loại, **ẩn** `Switch` khi `config.enabled === true` (chỉ bật được qua chọn process, vì `apply_process` bật sẵn) và ghi lại trong commit; không sửa serializer core. (b) `Switch.onCheckedChange` truyền `boolean` (xem `auto-close-automation.tsx:111`). (c) `Button` nhận `role`/`aria-checked` (prop HTML được forward) — nếu type không cho, bỏ `role="radiogroup"`/`role="radio"` và giữ `aria-pressed` qua `aria-pressed={config?.process === process}` nếu được, nếu không thì bỏ hẳn (biến thể primary/secondary vẫn thể hiện trạng thái kèm nhãn chữ).
- [ ] **Step 4:** allowlist thêm `packages/constants/src/settings/project.ts`, `apps/web/components/settings/project/sidebar/item-icon.tsx` (`settings.ts`, `extended.ts` đã thêm ở Task 11).
- [ ] **Step 5:** check types/lint/format → PASS.
- [ ] **Step 6: Commit** — `feat(ee/web): project settings tab for work item types`.

---

### Task 13: Các locale còn lại (skill `translate`)

`check:sync --ci` fail khi locale thiếu key. Spec: "locale khác theo skill translate".

**Files:**
- Modify: `packages/i18n/src/locales/<mọi locale trừ en, vi-VN>/work-item-type.json` (đã có glob allowlist ở Task 6)

- [ ] **Step 1:** Liệt kê locale: `ls packages/i18n/src/locales`. Với mỗi locale, invoke skill `translate` cho đúng khối `work_item_types.ee` của `en/work-item-type.json` (Task 6), giữ nguyên cấu trúc key, placeholder `{name}`, `#`/`{count, plural, ...}` với **đủ** các plural category của locale theo bảng CLDR trong skill (ru/ua/pl/cs/sk cần `one/few/many/other`), giữ "Scrum", "Agile", "Product Backlog", "User Story" nếu skill không có glossary khác, dịch "Epic" theo glossary.
- [ ] **Step 2:** `pnpm --filter @plane/i18n check:sync` → mọi locale 100% (không missing, không collision, không path conflict). `pnpm --filter @plane/i18n check:types && pnpm fix:format`.
- [ ] **Step 3: Commit** — `feat(i18n): work item type strings for remaining locales`.

---

### Task 14: Kiểm tra cuối (không cần trình duyệt)

**Files:** không sửa code (chỉ sửa allowlist nếu guard báo thiếu).

- [ ] **Step 1:** `pnpm --filter web test` → PASS.
- [ ] **Step 2:** `pnpm check:types` và `pnpm check:lint` ở gốc → PASS (oxlint `--max-warnings` của `apps/web` là ngưỡng; nếu vượt do file mới, sửa warning trong file mới, không nâng ngưỡng).
- [ ] **Step 3:** `pnpm fix:format && git status --short` → không còn thay đổi format chưa commit.
- [ ] **Step 4:** `pnpm --filter @plane/i18n check:sync` → PASS.
- [ ] **Step 5:** `pnpm --filter web exec react-router routes | grep work-item-types` → 2 dòng (workspace + project).
- [ ] **Step 6:** `pnpm --filter web build` → PASS (bắt lỗi import `../ee` của route).
- [ ] **Step 7:** Guard — `git fetch origin preview && BASE=origin/preview sh deployments/ee/check-core-untouched.sh` → `OK: only plugin-owned and allow-listed files changed.` Danh sách seam frontend phải khớp mục "Core files" ở Self-review.
- [ ] **Step 8:** Backend hồi quy (Task 1): `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/work_item_types` → PASS.
- [ ] **Step 9:** Smoke thủ công cho người duyệt (ghi vào PR, không tự động): tạo work item ở project Agile → select hiện User Story mặc định; chọn cha Story → chỉ Task/Sub-task bật, còn lại mờ kèm lý do; tạo sub-issue từ Feature → tự chọn User Story; đổi type trong peek sang Sub-task cho item có con → toast lỗi server, giá trị cũ giữ; filter Type=Epic ở list; Workspace Settings tạo/sửa/xoá (409 → chọn type chuyển); Project Settings đổi Scrum/Agile, gán/bỏ gán, default.
- [ ] **Step 10: Commit** (nếu có sửa allowlist) — `chore(ee): allow-list work item type frontend seams`.

---

## Self-review (đối chiếu spec)

**Spec coverage**
- `IssueTypeSelect` icon+màu, mờ + lý do khi có cha, nhớ type gần nhất (localStorage try/catch), sub-issue nhanh theo level liền dưới: Task 4 (logic + test), 7, 8. Parent picker lọc theo level: Task 8 (`filterIssue`, dùng `type_id` mà search API đã trả).
- `IssueTypeBadge` aria-label + tooltip, nhãn "Đã tắt": Task 7, gắn một chỗ ở `IssueIdentifier` (Task 9) phủ list/kanban/spreadsheet/peek/sub-issues.
- Tải lỗi / chưa bật → ẩn, không chặn: `getProjectTypes` trả `[]` → select/badge/filter ẩn (Task 5, 7, 10). Đổi type lỗi → toast, giữ giá trị (Task 7 Step 5–6).
- Store MobX theo project + workspace, `defaultTypeId`, `isEpic`, lọc type hợp lệ theo cha: Task 4–5.
- Workspace Settings CRUD, icon/màu/nền, level, epic, xoá + `migrate_to`, empty state gợi ý preset, cảnh báo low_contrast: Task 11. Project Settings Scrum/Agile, gán/bỏ gán, default, bật/tắt, trạng thái "Tuỳ chỉnh": Task 12. Quyền: ẩn/NotAuthorized theo `allowPermissions` (Task 11–12), server vẫn 403.
- Filter Type cho rich filters (cần để lọc Epic): Task 1 (backend) + Task 10.
- i18n en/vi-VN + locale khác + cơ chế fallback: Task 6, 13. Test frontend: Task 2, 4, 5. Allowlist + guard: mỗi task + Task 14.
- Epic đi luồng ISSUES (không `is_epic`): xác minh bằng grep ở Task 9 Step 4.

**Core files frontend chạm** (đều vào allowlist): `apps/web/package.json`, `pnpm-lock.yaml`, `packages/types/src/{work-item-types.ts,index.ts,view-props.ts,settings.ts}`, `packages/constants/src/issue/filter.ts`, `packages/constants/src/settings/{workspace.ts,project.ts}`, `packages/i18n/src/locales/*/work-item-type.json`, `apps/web/app/routes/extended.ts`, `apps/web/components/issues/issue-modal/provider.tsx`, `.../issue-modal/components/default-properties.tsx`, `apps/web/components/issues/parent-issues-list-modal.tsx`, `apps/web/components/issues/issue-detail/issue-identifier.tsx`, `apps/web/components/issues/issue-type-switcher.tsx`, `apps/web/hooks/work-item-filters/use-work-item-filters-config.tsx`, `apps/web/components/settings/{workspace,project}/sidebar/item-icon.tsx`. Backend: `apps/api/plane/utils/filters/filterset.py`.

**Không sửa (chủ ý)**: từng block list/kanban/spreadsheet (phủ qua `IssueIdentifier`); `root.store.ts` (store là singleton plugin); `issue-detail/parent-select.tsx` (server vẫn validate).

**Giới hạn đã biết**: issue cũ `type_id=null` không khớp filter Type (badge thì hiển thị default); type đã bị bỏ gán khỏi project không hiện badge (project endpoint chỉ trả type đã gán); `IssueTypeSelect` ở `mode="edit"` mờ type theo cha chỉ khi cha có trong store.

**Placeholder scan**: mọi bước code có code thật; các điểm không biết chắc khi chưa chạy app được viết thành bước "Xác minh giả định" kèm phương án thay thế cụ thể (Task 7 Step 6, 8 Step 5, 10 Step 4–5, 11 Step 1/3/4/5, 12 Step 3).

**Type consistency**: `TProjectIssueType` dùng xuyên suốt rules/store/select/filter; `onChange(typeId, { auto })` khớp giữa `IssueTypeSelect` ↔ `IssueTypeFormField` ↔ `IssueTypeChange` (bỏ qua `meta`); `parentTypeId: undefined` = "không rõ" (không mờ) vs `null` = cha legacy (default) — áp dụng nhất quán ở `IssueTypeSelect` (Task 7 Step 3), Task 8 Step 2, `IssueTypeChange`. Store methods tên khớp giữa Task 5 Interfaces, pages Task 11–12 và test.
