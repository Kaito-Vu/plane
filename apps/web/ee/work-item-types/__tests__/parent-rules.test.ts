import { describe, expect, it } from "vitest";
import { PARENT_RULES_UI, TYPE_KEYS, childTypesOf } from "../constants";

describe("PARENT_RULES_UI helpers", () => {
  it("childTypesOf inverts the parent rules", () => {
    expect(childTypesOf("epic")).toEqual(["epic", "feature"]);
    expect(childTypesOf("user_story")).toEqual(["task", "bug"]);
    expect(childTypesOf("task")).toEqual(["bug", "sub_task"]);
    expect(childTypesOf("sub_task")).toEqual([]);
  });

  it("every allowed parent is itself a known type", () => {
    for (const key of TYPE_KEYS) for (const parent of PARENT_RULES_UI[key]) expect(TYPE_KEYS).toContain(parent);
  });
});
