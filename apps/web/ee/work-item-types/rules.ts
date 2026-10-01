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
