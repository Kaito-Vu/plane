/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TIssueType } from "@plane/types";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useUserPermissions } from "@/hooks/store/user";
import { TypeDeleteDialog } from "../components/type-delete-dialog";
import { TypeFormDialog } from "../components/type-form-dialog";
import { useTypeName } from "../components/type-name";
import { useWorkItemTypes, useWorkspaceWorkItemTypes } from "../hooks";

function WorkspaceWorkItemTypesPage() {
  const { workspaceSlug: slugParam } = useParams();
  const workspaceSlug = slugParam?.toString() ?? "";
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const types = useWorkspaceWorkItemTypes(isAdmin ? workspaceSlug : undefined);
  const [editing, setEditing] = useState<TIssueType | "new" | null>(null);
  const [deleting, setDeleting] = useState<TIssueType | null>(null);

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" className="h-auto" />;

  // oxlint-disable-next-line unicorn/no-array-sort -- copy; TS lib lacks toSorted
  const sorted = [...(types ?? [])].sort((a, b) => b.level - a.level || a.name.localeCompare(b.name));

  return (
    <SettingsContentWrapper>
      <PageHead title={t("work_item_types.label")} />
      <SettingsHeading
        title={t("work_item_types.label")}
        description={t("work_item_types.ee.workspace.description")}
        control={
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label={t("work_item_types.create.button")}
            onClick={() => setEditing("new")}
          />
        }
      />
      {types && sorted.length === 0 && (
        <div className="mt-6 rounded-md border border-subtle p-6">
          <p className="text-body-sm-medium">{t("work_item_types.ee.workspace.empty_title")}</p>
          <p className="text-body-xs-regular text-tertiary">{t("work_item_types.ee.workspace.empty_description")}</p>
        </div>
      )}
      <ul className="mt-6 flex flex-col divide-y divide-subtle">
        {sorted.map((type) => (
          <li key={type.id} className="flex items-center gap-3 py-3">
            <span
              className="flex size-7 items-center justify-center rounded-md"
              style={{ backgroundColor: type.logo_props.icon?.background_color }}
            >
              <Logo logo={type.logo_props} size={16} type="lucide" />
            </span>
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-body-sm-medium">{typeName(type)}</span>
              <span className="text-body-xs-regular text-tertiary">
                {t("work_item_types.ee.workspace.level")} {type.level}
                {type.is_preset && ` · ${t("work_item_types.ee.workspace.preset_badge")}`}
                {type.low_contrast && ` · ${t("work_item_types.ee.workspace.low_contrast")}`}
              </span>
            </div>
            <Button variant="secondary" size="sm" stretch="auto" label={t("edit")} onClick={() => setEditing(type)} />
            {!type.is_preset && (
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label={t("delete")}
                onClick={() => setDeleting(type)}
              />
            )}
          </li>
        ))}
      </ul>
      <TypeFormDialog
        isOpen={editing !== null}
        type={editing && editing !== "new" ? editing : undefined}
        onClose={() => setEditing(null)}
        onSubmit={(data) =>
          editing && editing !== "new"
            ? store.updateType(workspaceSlug, editing.id, data)
            : store.createType(workspaceSlug, data)
        }
      />
      <TypeDeleteDialog
        type={deleting}
        candidates={sorted.filter((c) => c.id !== deleting?.id && c.is_active && c.level === deleting?.level)}
        onClose={() => setDeleting(null)}
        onDelete={(migrateTo) => store.deleteType(workspaceSlug, deleting!.id, migrateTo)}
      />
    </SettingsContentWrapper>
  );
}

export default observer(WorkspaceWorkItemTypesPage);
