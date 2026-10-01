/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import { WorkItemsOutline } from "@makeplane/propel/icons";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import type { TFilterConfig, TLogoProps, TProjectIssueType, TWorkItemFilterProperty } from "@plane/types";
import { COLLECTION_OPERATOR, EQUALITY_OPERATOR } from "@plane/types";
import type { TCreateFilterConfigParams } from "@plane/utils";
import { createFilterConfig, createOperatorConfigEntry, getMultiSelectConfig } from "@plane/utils";
import { useProjectWorkItemTypes, useWorkItemTypes } from "./hooks";
import { useTypeName } from "./components/type-name";

type TParams = {
  workspaceSlug: string;
  projectId: string | undefined;
  isEnabled: boolean;
  operatorConfigs: Omit<TCreateFilterConfigParams, "isEnabled">;
};

export function useWorkItemTypeFilterConfig(params: TParams): TFilterConfig<TWorkItemFilterProperty> {
  const { workspaceSlug, projectId, isEnabled, operatorConfigs } = params;
  useProjectWorkItemTypes(workspaceSlug, projectId);
  const types = useWorkItemTypes().getProjectTypes(projectId);
  const typeName = useTypeName();

  return useMemo(() => {
    const base = { isEnabled: isEnabled && types.length > 0, ...operatorConfigs };
    return createFilterConfig<TWorkItemFilterProperty>({
      id: "type_id",
      label: "Type",
      ...base,
      icon: WorkItemsOutline,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, base, (updatedParams) =>
          getMultiSelectConfig<TProjectIssueType, string, TLogoProps>(
            {
              items: types,
              getId: (type) => type.id,
              getLabel: (type) => typeName(type),
              getValue: (type) => type.id,
              getIconData: (type) => type.logo_props,
            },
            { singleValueOperator: EQUALITY_OPERATOR.EXACT, ...updatedParams },
            { getOptionIcon: (logo) => <Logo logo={logo} size={12} type="lucide" /> }
          )
        ),
      ]),
    });
  }, [isEnabled, operatorConfigs, types, typeName]);
}
