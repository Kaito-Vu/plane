/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { MutableRefObject } from "react";
// components
import type { TIssue, IIssueDisplayProperties, TIssueMap, TGroupedIssues } from "@plane/types";
// hooks
import type { TSelectionHelper } from "@/hooks/use-multiple-select";
// types
import { IssueBlockRoot } from "./block-root";
import type { TRenderQuickActions } from "./list-view-types";

interface Props {
  issueIds: TGroupedIssues | any;
  issuesMap: TIssueMap;
  groupId: string;
  canEditProperties: (projectId: string | undefined) => boolean;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  quickActions: TRenderQuickActions;
  displayProperties: IIssueDisplayProperties | undefined;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  isDragAllowed: boolean;
  canDropOverIssue: boolean;
  selectionHelpers: TSelectionHelper;
  isEpic?: boolean;
}

// Orders a flat id list depth-first by parent_id (children right under their parent).
// Items whose parent is not in the list are treated as roots.
const orderAsTree = (ids: string[], issuesMap: TIssueMap) => {
  const present = new Set(ids);
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  ids.forEach((id) => {
    const parentId = issuesMap[id]?.parent_id;
    if (parentId && parentId !== id && present.has(parentId))
      children.set(parentId, [...(children.get(parentId) ?? []), id]);
    else roots.push(id);
  });
  const out: { id: string; depth: number }[] = [];
  const seen = new Set<string>();
  const walk = (id: string, depth: number) => {
    if (seen.has(id)) return;
    seen.add(id);
    out.push({ id, depth });
    children.get(id)?.forEach((c) => walk(c, depth + 1));
  };
  roots.forEach((id) => walk(id, 0));
  return out;
};

export function IssueBlocksList(props: Props) {
  const {
    issueIds,
    issuesMap,
    groupId,
    updateIssue,
    quickActions,
    displayProperties,
    canEditProperties,
    containerRef,
    selectionHelpers,
    isDragAllowed,
    canDropOverIssue,
    isEpic = false,
  } = props;

  const rows = Array.isArray(issueIds) ? orderAsTree(issueIds, issuesMap) : [];

  return (
    <div className="relative h-full w-full">
      {rows.length > 0 &&
        rows.map(({ id: issueId, depth }, index) => (
          <IssueBlockRoot
            key={issueId}
            issueId={issueId}
            issuesMap={issuesMap}
            updateIssue={updateIssue}
            quickActions={quickActions}
            canEditProperties={canEditProperties}
            displayProperties={displayProperties}
            nestingLevel={depth}
            spacingLeft={depth * 24}
            hideExpand
            containerRef={containerRef}
            selectionHelpers={selectionHelpers}
            groupId={groupId}
            isLastChild={index === rows.length - 1}
            isDragAllowed={isDragAllowed}
            canDropOverIssue={canDropOverIssue}
            isEpic={isEpic}
          />
        ))}
    </div>
  );
}
