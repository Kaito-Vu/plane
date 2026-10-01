/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
import type { ISearchIssueResponse } from "@plane/types";
import { hierarchyReason } from "./rules";
import { WorkItemTypeService } from "./service";
import { WorkItemTypeStore } from "./store";

// ponytail: module singleton instead of a root-store slot (no core edit); data is keyed by slug/project id so it
// does not leak across workspaces. Add a reset on sign-out if stale types after switching accounts become a problem.
const store = new WorkItemTypeStore(new WorkItemTypeService());
const SWR_OPTIONS = {
  revalidateOnFocus: false,
  revalidateIfStale: false,
  revalidateOnReconnect: false,
  shouldRetryOnError: false,
} as const;

export const useWorkItemTypes = () => store;

/**
 * Loads once per project (SWR dedupes the many badges of a list; the key goes null once the store has the project so
 * list rows never refetch). `fresh` (settings pages) always revalidates on mount. Call from an observer component.
 */
export function useProjectWorkItemTypesQuery(
  workspaceSlug: string | undefined,
  projectId: string | null | undefined,
  fresh = false
) {
  const { error, mutate } = useSWR(
    workspaceSlug && projectId && (fresh || !store.getProject(projectId))
      ? ["WORK_ITEM_TYPES_PROJECT", workspaceSlug, projectId, fresh]
      : null,
    ([, slug, pid]: [string, string, string]) => store.fetchProject(slug, pid),
    fresh ? { ...SWR_OPTIONS, revalidateIfStale: true } : SWR_OPTIONS
  );
  return { config: store.getProject(projectId), error, retry: () => mutate() };
}

export const useProjectWorkItemTypes = (workspaceSlug: string | undefined, projectId: string | null | undefined) =>
  useProjectWorkItemTypesQuery(workspaceSlug, projectId).config;

export function useWorkspaceWorkItemTypesQuery(workspaceSlug: string | undefined) {
  const { error, mutate } = useSWR(
    workspaceSlug ? ["WORK_ITEM_TYPES_WORKSPACE", workspaceSlug] : null,
    ([, slug]: [string, string]) => store.fetchWorkspace(slug),
    { ...SWR_OPTIONS, revalidateIfStale: true }
  );
  return { types: store.getWorkspaceTypes(workspaceSlug), error, retry: () => mutate() };
}

export const useWorkspaceWorkItemTypes = (workspaceSlug: string | undefined) =>
  useWorkspaceWorkItemTypesQuery(workspaceSlug).types;

/** Parent picker filter: keep only issues whose type may parent the chosen type. undefined = no filtering. */
export function useParentIssueFilter(projectId: string | null | undefined, typeId: string | null | undefined) {
  const child = store.resolveType(projectId, typeId);
  if (!child) return undefined;
  return (issue: ISearchIssueResponse) => {
    // type_id undefined = server did not say: keep it (resolveType(undefined) would wrongly mean "project default")
    if (issue.type_id === undefined) return true;
    const parent = store.resolveType(projectId, issue.type_id);
    return !parent || hierarchyReason(child, parent) === null;
  };
}
