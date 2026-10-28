import type { TWorkItemTypeKey } from "./types";

// Mirror of apps/api/plane/ee/work_item_types/constants.py (synced by a test in Task 15).
export const PARENT_RULES_UI: Record<TWorkItemTypeKey, TWorkItemTypeKey[]> = {
  epic: ["epic"],
  feature: ["epic", "feature"],
  user_story: ["feature"],
  task: ["user_story"],
  bug: ["task", "user_story"],
  sub_task: ["task", "bug"],
};

export const SPRINT_TYPES_UI: TWorkItemTypeKey[] = ["user_story", "task", "bug", "sub_task"];

export const TYPE_KEYS: TWorkItemTypeKey[] = ["epic", "feature", "user_story", "task", "bug", "sub_task"];

/** Inverse of PARENT_RULES_UI: types that may be created under a parent of the given type. */
export const childTypesOf = (parentKey: TWorkItemTypeKey): TWorkItemTypeKey[] =>
  TYPE_KEYS.filter((k) => PARENT_RULES_UI[k].includes(parentKey));

/** Badge colour per type (hex, used inline). */
export const TYPE_COLORS: Record<TWorkItemTypeKey, string> = {
  epic: "#7c3aed",
  feature: "#2563eb",
  user_story: "#16a34a",
  task: "#0891b2",
  bug: "#dc2626",
  sub_task: "#64748b",
};
