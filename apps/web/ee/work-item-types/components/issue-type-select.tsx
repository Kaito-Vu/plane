/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef } from "react";
import { observer } from "mobx-react";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { Pill as PillChrome } from "@makeplane/propel/elements/pill";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useTranslation } from "@plane/i18n";
import { useProjectWorkItemTypes, useWorkItemTypes } from "../hooks";
import { initialTypeId, suggestedChildTypeId, typeOptionsForParent, writeLastTypeId } from "../rules";
import { useTypeName } from "./type-name";

export type TIssueTypeSelectProps = {
  workspaceSlug: string;
  projectId: string | null;
  value: string | null | undefined;
  /** create: pre-fill (last used / default) and follow the parent; edit: never change the value by itself. */
  mode: "create" | "edit";
  hasParent: boolean;
  /** Parent's type_id; null = legacy parent (treated as project default); ignored when hasParent is false. */
  parentTypeId: string | null | undefined;
  onChange: (typeId: string, meta: { auto: boolean }) => void;
  disabled?: boolean;
  tabIndex?: number;
};

export const IssueTypeSelect = observer(function IssueTypeSelect(props: TIssueTypeSelectProps) {
  const { workspaceSlug, projectId, value, mode, hasParent, parentTypeId, onChange, disabled, tabIndex } = props;
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  useProjectWorkItemTypes(workspaceSlug, projectId);
  const types = store.getProjectTypes(projectId);
  // null = no parent; undefined = parent's type unknown → nothing muted (resolveType(undefined) would give the default)
  const parentType = !hasParent
    ? null
    : parentTypeId === undefined
      ? undefined
      : store.resolveType(projectId, parentTypeId);
  const pickedByUser = useRef(false);

  // create: fill an empty/stale value once types arrive (the provider seam covers the already-loaded case)
  useEffect(() => {
    if (mode !== "create" || !projectId || !types.length) return;
    if (value && types.some((type) => type.id === value)) return;
    const id = initialTypeId(types, projectId);
    if (id) onChange(id, { auto: true });
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [mode, projectId, types]);

  // create: quick sub-issue → level right below the parent, until the user picks something
  useEffect(() => {
    if (mode !== "create" || pickedByUser.current || !parentType) return;
    const id = suggestedChildTypeId(types, parentType);
    if (id && id !== value) onChange(id, { auto: true });
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [mode, parentType?.id, types]);

  if (!projectId || !types.length) return null; // feature off / load failed → no select, creation not blocked

  const current = store.resolveType(projectId, value);
  const options = typeOptionsForParent(types, parentType);

  return (
    <Menu>
      <MenuTrigger
        disabled={disabled}
        tabIndex={tabIndex}
        aria-label={`${t("work_item_types.ee.field_label")}: ${current ? typeName(current) : t("work_item_types.ee.placeholder")}`}
        render={
          <PillChrome size="sm" variant="outline">
            {current && <Logo logo={current.logo_props} size={14} type="lucide" />}
            <span>{current ? typeName(current) : t("work_item_types.ee.placeholder")}</span>
          </PillChrome>
        }
      />
      <MenuContent side="bottom" align="start">
        {options.map(({ type, reason }) => (
          <MenuItem
            key={type.id}
            label={typeName(type)}
            // muted with the reason shown, so it is readable without hovering
            description={reason ? t(`work_item_types.ee.reason.${reason}`) : undefined}
            icon={<Logo logo={type.logo_props} size={14} type="lucide" />}
            disabled={!!reason}
            onClick={() => {
              pickedByUser.current = true;
              writeLastTypeId(projectId, type.id);
              onChange(type.id, { auto: false });
            }}
          />
        ))}
      </MenuContent>
    </Menu>
  );
});
