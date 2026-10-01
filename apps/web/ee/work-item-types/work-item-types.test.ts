/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

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
