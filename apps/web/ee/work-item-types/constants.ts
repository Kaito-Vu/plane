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
