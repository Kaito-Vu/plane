/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { firstErrorMessage } from "../rules";
import { IssueTypeSelect } from "./issue-type-select";

type Props = { issueId: string; disabled: boolean };

/** Change type of an existing work item through the normal issue PATCH (server validates parent/children). */
export const IssueTypeChange = observer(function IssueTypeChange({ issueId, disabled }: Props) {
  const { workspaceSlug } = useParams();
  const { t } = useTranslation();
  const {
    issue: { getIssueById },
    updateIssue,
  } = useIssueDetail();
  const issue = getIssueById(issueId);
  const parent = issue?.parent_id ? getIssueById(issue.parent_id) : undefined;
  if (!workspaceSlug || !issue?.project_id) return null;
  const projectId = issue.project_id;

  return (
    <IssueTypeSelect
      workspaceSlug={workspaceSlug.toString()}
      projectId={projectId}
      value={issue.type_id}
      mode="edit"
      hasParent={!!issue.parent_id}
      // parent not in the store → undefined parent type → nothing muted, the server still validates
      parentTypeId={parent ? parent.type_id : undefined}
      disabled={disabled}
      onChange={async (typeId) => {
        if (typeId === issue.type_id) return;
        try {
          await updateIssue(workspaceSlug.toString(), projectId, issueId, { type_id: typeId });
        } catch (error) {
          setToast({
            type: "error",
            title: t("work_item_types.update.toast.error.title"),
            message: firstErrorMessage(error) ?? t("work_item_types.ee.change_failed"),
          });
        }
      }}
    />
  );
});
