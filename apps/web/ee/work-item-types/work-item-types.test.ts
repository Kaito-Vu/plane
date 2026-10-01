/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import type { TProjectIssueType } from "@plane/types";
import {
  defaultTypeId,
  contrastRatio,
  firstErrorMessage,
  isLowContrast,
  levelMeaningKey,
  resolveParentTypeId,
  typeSelectMode,
  hierarchyReason,
  initialTypeId,
  presetLabelKey,
  readLastTypeId,
  suggestedChildTypeId,
  typeOptionsForParent,
  writeLastTypeId,
} from "./rules";
import { WorkItemTypeStore } from "./store";

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
    expect(presetLabelKey({ ...EPIC, name: "Epic" })).toBe("work_item_types.ee.preset.epic");
    expect(presetLabelKey({ ...STORY, name: "User Story" })).toBe("work_item_types.ee.preset.user_story");
    // renamed by an admin: show the admin's name, not the translation
    expect(presetLabelKey({ ...EPIC, name: "Initiative" })).toBeNull();
    expect(presetLabelKey(mkType({ id: "spike", level: 1, is_preset: false, external_id: null }))).toBeNull();
  });
  it("typeSelectMode is edit only for an existing non-draft issue", () => {
    expect(typeSelectMode(undefined, false)).toBe("create");
    expect(typeSelectMode("i1", true)).toBe("create");
    expect(typeSelectMode("i1", false)).toBe("edit");
  });
  it("resolveParentTypeId keeps null (legacy) and unknown (undefined) apart", () => {
    expect(resolveParentTypeId(null, "x")).toBeNull();
    expect(resolveParentTypeId(undefined, "x")).toBe("x");
    expect(resolveParentTypeId("", undefined)).toBeUndefined();
    expect(resolveParentTypeId("t1", "x")).toBe("t1");
  });
  it("contrast ratio follows WCAG", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 0);
    expect(contrastRatio("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 5);
    expect(contrastRatio("red", "#FFFFFF")).toBeNull();
    expect(isLowContrast("#CCCCCC", "#FFFFFF")).toBe(true);
    expect(isLowContrast("#1D4ED8", "#FFFFFF")).toBe(false);
    expect(isLowContrast("nope", "#FFFFFF")).toBe(false);
  });
  it("levelMeaningKey covers 0..4 else generic", () => {
    expect(levelMeaningKey(0)).toBe("work_item_types.ee.workspace.level_meaning.0");
    expect(levelMeaningKey(7)).toBe("work_item_types.ee.workspace.level_meaning.other");
  });
  it("firstErrorMessage reads nested bodies", () => {
    expect(firstErrorMessage({ error: { parent_id: "bad parent" } })).toBe("bad parent");
  });
  it("firstErrorMessage reads DRF bodies", () => {
    expect(firstErrorMessage({ type_id: ["Invalid work item type"] })).toBe("Invalid work item type");
    expect(firstErrorMessage({ error: "This type cannot be deleted", count: 3 })).toBe("This type cannot be deleted");
    expect(firstErrorMessage(undefined)).toBeNull();
  });
});

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
