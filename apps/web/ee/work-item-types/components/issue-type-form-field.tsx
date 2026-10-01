/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useFormContext, useWatch } from "react-hook-form";
import type { TIssue } from "@plane/types";
import { IssueTypeSelect } from "./issue-type-select";

type Props = {
  workspaceSlug: string;
  projectId: string | null;
  hasParent: boolean;
  parentTypeId: string | null | undefined;
  onUserChange: () => void;
  tabIndex?: number;
};

/** Lives inside issue-modal/form.tsx's FormProvider. Auto picks do not dirty the form (no discard prompt). */
export const IssueTypeFormField = observer(function IssueTypeFormField(props: Props) {
  const { onUserChange, ...rest } = props;
  const { control, setValue } = useFormContext<TIssue>();
  const value = useWatch({ control, name: "type_id" });
  return (
    <IssueTypeSelect
      {...rest}
      mode="create"
      value={value}
      onChange={(typeId, { auto }) => {
        setValue("type_id", typeId, { shouldDirty: !auto, shouldValidate: true });
        if (!auto) onUserChange();
      }}
    />
  );
});
