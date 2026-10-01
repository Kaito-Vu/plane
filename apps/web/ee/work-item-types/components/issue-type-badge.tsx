/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useProjectWorkItemTypes, useWorkItemTypes } from "../hooks";
import { useTypeName } from "./type-name";

type Props = { projectId: string; typeId: string | null | undefined; size?: number };

export const IssueTypeBadge = observer(function IssueTypeBadge({ projectId, typeId, size = 14 }: Props) {
  const { workspaceSlug } = useParams();
  useProjectWorkItemTypes(workspaceSlug?.toString(), projectId);
  const store = useWorkItemTypes();
  const typeName = useTypeName();
  const type = store.resolveType(projectId, typeId);
  if (!type) return null;
  const label = typeName(type);
  return (
    <Tooltip label={label}>
      {/* the name is in aria-label + tooltip (focusable so keyboard users get the tooltip), never colour alone */}
      <span role="img" tabIndex={0} aria-label={label} className="inline-flex shrink-0 items-center">
        <Logo logo={type.logo_props} size={size} type="lucide" />
      </span>
    </Tooltip>
  );
});
