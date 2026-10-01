/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

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
export function typeOptionsForParent(types: TProjectIssueType[], parent: TLevelInfo | null | undefined): TTypeOption[] {
  return (
    types
      .filter((type) => type.is_active) // filter() already copies, so sort() below is non-mutating
      // oxlint-disable-next-line unicorn/no-array-sort -- web tsconfig lib lacks ES2023 toSorted
      .sort((a, b) => b.level - a.level || a.name.localeCompare(b.name))
      .map((type) => ({ type, reason: parent === undefined ? null : hierarchyReason(type, parent) }))
  );
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

// Seeded English names, mirroring the backend presets (apps/api/plane/ee/work_item_types presets).
export const SEEDED_PRESET_NAMES: Record<string, string> = {
  epic: "Epic",
  feature: "Feature",
  bug: "Bug",
  task: "Task",
  sub_task: "Sub-task",
  product_backlog_item: "Product Backlog Item",
  user_story: "User Story",
};

/** A preset is translated only while it still carries its seeded name; a renamed preset shows the admin's name. */
export const presetLabelKey = (type: Pick<TIssueType, "name" | "is_preset" | "external_id">): string | null =>
  type.is_preset && type.external_id && SEEDED_PRESET_NAMES[type.external_id] === type.name
    ? `work_item_types.ee.preset.${type.external_id}`
    : null;

/** Editing an existing (non-draft) work item must never change its type by itself. */
export const typeSelectMode = (issueId: string | null | undefined, isDraft: boolean): "create" | "edit" =>
  issueId && !isDraft ? "edit" : "create";

/** Parent's type: search result wins; undefined/"" (not sent / preloaded empty) falls back to the store, still undefined = unknown. */
export const resolveParentTypeId = (
  fromSearch: string | null | undefined,
  fromStore: string | null | undefined
): string | null | undefined => (fromSearch === undefined || fromSearch === "" ? fromStore : fromSearch);

/** i18n key for the meaning of a level (0 = sub-task … 4 = epic), generic for the rest. */
export const levelMeaningKey = (level: number) =>
  Number.isInteger(level) && level >= 0 && level <= 4
    ? `work_item_types.ee.workspace.level_meaning.${level}`
    : "work_item_types.ee.workspace.level_meaning.other";

const luminance = (hex: string): number | null => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** WCAG 2.x contrast ratio of two #RRGGBB colours; null when either is not a 6-digit hex. */
export function contrastRatio(a: string, b: string): number | null {
  const la = luminance(a);
  const lb = luminance(b);
  if (la === null || lb === null) return null;
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export const isLowContrast = (color: string | undefined, background: string | undefined): boolean => {
  const ratio = contrastRatio(color ?? "", background ?? "#FFFFFF");
  return ratio !== null && ratio < 4.5;
};

/** First human message of a DRF error body ({field: [msg]}, {error: msg} or nested {error: {field: msg}}). */
export function firstErrorMessage(err: unknown, depth = 0): string | null {
  if (!err || typeof err !== "object" || depth > 2) return null;
  for (const value of Object.values(err as Record<string, unknown>)) {
    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const nested = firstErrorMessage(value, depth + 1);
      if (nested) return nested;
    }
  }
  return null;
}
