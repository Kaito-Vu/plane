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
