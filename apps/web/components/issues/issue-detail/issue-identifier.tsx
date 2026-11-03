/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import type { TIssueIdentifierProps } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { IdentifierText } from "@/components/issues/issue-detail/identifier-text";
import { TypeBadge } from "@/ee/work-item-types/components/type-badge";

export const IssueIdentifier = observer(function IssueIdentifier(props: TIssueIdentifierProps) {
  const {
    projectId,
    variant,
    size,
    displayProperties,
    enableClickToCopyIdentifier = false,
    fullTypeBadge = false,
  } = props;
  // store hooks
  const { getProjectIdentifierById } = useProject();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  // Determine if the component is using store data or not
  const isUsingStoreData = "issueId" in props;
  // derived values
  const issue = isUsingStoreData ? getIssueById(props.issueId) : null;
  const projectIdentifier = isUsingStoreData ? getProjectIdentifierById(projectId) : props.projectIdentifier;
  const issueSequenceId = isUsingStoreData ? issue?.sequence_id : props.issueSequenceId;
  const shouldRenderIssueID = displayProperties ? displayProperties.key : true;
  const shouldRenderType = displayProperties?.issue_type !== false; // saved prefs that predate the property keep showing it

  if (!shouldRenderIssueID && !shouldRenderType) return null;

  return (
    <div className="flex shrink-0 items-center space-x-2">
      {shouldRenderType && (
        <TypeBadge
          projectId={projectId}
          typeId={isUsingStoreData ? issue?.type_id : props.issueTypeId}
          compact={!fullTypeBadge}
        />
      )}
      {shouldRenderIssueID && (
        <IdentifierText
          identifier={`${projectIdentifier}-${issueSequenceId}`}
          enableClickToCopyIdentifier={enableClickToCopyIdentifier}
          variant={variant}
          size={size}
        />
      )}
    </div>
  );
});
