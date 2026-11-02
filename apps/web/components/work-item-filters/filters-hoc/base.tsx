/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useRef } from "react";
import { observer } from "mobx-react";
import { v4 as uuidv4 } from "uuid";
// plane imports
import type { TSaveViewOptions, TUpdateViewOptions } from "@plane/constants";
import type { IWorkItemFilterInstance } from "@plane/shared-state";
import type { IIssueFilters, TWorkItemFilterExpression } from "@plane/types";
// store hooks
import { useWorkItemFilters } from "@/hooks/store/work-item-filters/use-work-item-filters";
// plane web imports
import type { TWorkItemFiltersEntityProps } from "@/hooks/work-item-filters/use-work-item-filters-config";
import { useWorkItemFiltersConfig } from "@/hooks/work-item-filters/use-work-item-filters-config";
// local imports
import type { TSharedWorkItemFiltersHOCProps, TSharedWorkItemFiltersProps } from "./shared";

type TAdditionalWorkItemFiltersProps = {
  saveViewOptions?: TSaveViewOptions<TWorkItemFilterExpression>;
  updateViewOptions?: TUpdateViewOptions<TWorkItemFilterExpression>;
} & TWorkItemFiltersEntityProps;

type TWorkItemFiltersHOCProps = TSharedWorkItemFiltersHOCProps & TAdditionalWorkItemFiltersProps;

export const WorkItemFiltersHOC = observer(function WorkItemFiltersHOC(props: TWorkItemFiltersHOCProps) {
  const { children, initialWorkItemFilters } = props;

  // Only initialize filter instance when initial work item filters are defined
  if (!initialWorkItemFilters)
    return <>{typeof children === "function" ? children({ filter: undefined }) : children}</>;

  return (
    <WorkItemFilterRoot {...props} initialWorkItemFilters={initialWorkItemFilters}>
      {children}
    </WorkItemFilterRoot>
  );
});

type TWorkItemFilterProps = TSharedWorkItemFiltersProps &
  TAdditionalWorkItemFiltersProps & {
    initialWorkItemFilters: IIssueFilters;
    children: React.ReactNode | ((props: { filter: IWorkItemFilterInstance }) => React.ReactNode);
  };

const WorkItemFilterRoot = observer(function WorkItemFilterRoot(props: TWorkItemFilterProps) {
  const {
    children,
    entityType,
    entityId,
    filtersToShowByLayout,
    initialWorkItemFilters,
    isTemporary,
    saveViewOptions,
    updateFilters,
    updateViewOptions,
    showOnMount,
    ...entityConfigProps
  } = props;
  // store hooks
  const { getOrCreateFilter, deleteFilter } = useWorkItemFilters();
  // derived values
  const workItemEntityID = useMemo(
    () => (isTemporary ? `TEMP-${entityId ?? uuidv4()}` : entityId),
    [isTemporary, entityId]
  );
  // memoize initial values to prevent re-computations when reference changes
  const initialUserFilters = useMemo(() => initialWorkItemFilters.richFilters, [initialWorkItemFilters]);
  const workItemFiltersConfig = useWorkItemFiltersConfig({
    allowedFilters: filtersToShowByLayout ? filtersToShowByLayout : [],
    ...entityConfigProps,
  });
  // get or create filter instance
  const workItemLayoutFilter = useMemo(
    () =>
      getOrCreateFilter({
        entityType,
        entityId: workItemEntityID,
        initialExpression: initialUserFilters,
        onExpressionChange: updateFilters,
        expressionOptions: {
          saveViewOptions,
          updateViewOptions,
        },
        showOnMount,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [entityType, workItemEntityID, saveViewOptions, updateViewOptions, updateFilters]
  );

  // delete filter instance when component unmounts. Deferred: StrictMode (dev) runs cleanup + re-mount
  // back to back, and the instance is created in useMemo (not re-run), so an immediate delete left the
  // page without a filter ("filter instance not available").
  const liveKeyRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const key = `${entityType}:${workItemEntityID}`;
    liveKeyRef.current = key;
    return () => {
      liveKeyRef.current = undefined;
      setTimeout(() => {
        if (liveKeyRef.current !== key) deleteFilter(entityType, workItemEntityID);
      }, 0);
    };
  }, [deleteFilter, entityType, workItemEntityID]);

  useEffect(() => {
    workItemLayoutFilter.configManager.setAreConfigsReady(workItemFiltersConfig.areAllConfigsInitialized);
    workItemLayoutFilter.configManager.registerAll(workItemFiltersConfig.configs);
  }, [
    workItemFiltersConfig.areAllConfigsInitialized,
    workItemFiltersConfig.configs,
    workItemLayoutFilter.configManager,
  ]);

  return <>{typeof children === "function" ? children({ filter: workItemLayoutFilter }) : children}</>;
});
