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

/** Badge colour per type (hex, used inline). Shades chosen for >= 4.5:1 text contrast on the light tint. */
export const TYPE_COLORS: Record<TWorkItemTypeKey, string> = {
  epic: "#6d28d9",
  feature: "#1d4ed8",
  user_story: "#15803d",
  task: "#0e7490",
  bug: "#b91c1c",
  sub_task: "#475569",
};
