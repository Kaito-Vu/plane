/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TWorkItemProcess } from "@plane/types";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useUserPermissions } from "@/hooks/store/user";
import { useTypeName } from "../components/type-name";
import { useProjectWorkItemTypes, useWorkItemTypes, useWorkspaceWorkItemTypes } from "../hooks";
import { firstErrorMessage } from "../rules";

const PROCESSES: TWorkItemProcess[] = ["scrum", "agile"];

function ProjectWorkItemTypesPage() {
  const params = useParams();
  const workspaceSlug = params.workspaceSlug?.toString() ?? "";
  const projectId = params.projectId?.toString() ?? "";
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const config = useProjectWorkItemTypes(isAdmin ? workspaceSlug : undefined, projectId);
  const workspaceTypes = useWorkspaceWorkItemTypes(isAdmin ? workspaceSlug : undefined);

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  // every action refetches the project; errors (409 in-use, 400 invalid) are shown verbatim from the server
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
    } catch (error) {
      setToast({
        type: "error",
        title: t("work_item_types.update.toast.error.title"),
        message: firstErrorMessage(error) ?? t("work_item_types.ee.project.action_failed"),
      });
    }
  };

  const assigned = config?.types ?? [];
  const assignedIds = new Set(assigned.map((type) => type.id));
  const available = (workspaceTypes ?? []).filter((type) => type.is_active && !assignedIds.has(type.id));

  return (
    <SettingsContentWrapper>
      <PageHead title={t("work_item_types.label")} />
      <SettingsHeading
        title={t("work_item_types.label")}
        description={t("work_item_types.ee.project.description")}
        control={
          config && (
            <label className="flex items-center gap-2 text-body-xs-regular">
              <Switch
                size="sm"
                checked={config.enabled}
                onCheckedChange={(enabled) => run(() => store.setEnabled(workspaceSlug, projectId, enabled))}
              />
              {t("work_item_types.ee.project.enabled")}
            </label>
          )
        }
      />
      <section className="mt-6 flex flex-col gap-2">
        <h4 className="text-body-sm-medium">{t("work_item_types.ee.project.process")}</h4>
        <div role="radiogroup" aria-label={t("work_item_types.ee.project.process")} className="flex gap-2">
          {PROCESSES.map((process) => (
            <Button
              key={process}
              role="radio"
              aria-checked={config?.process === process}
              variant={config?.process === process ? "primary" : "secondary"}
              size="md"
              stretch="auto"
              label={t(`work_item_types.ee.project.${process}`)}
              onClick={() => run(() => store.setProcess(workspaceSlug, projectId, process))}
            />
          ))}
          {config && config.enabled && config.process === null && (
            <span className="self-center text-body-xs-regular text-tertiary">
              {t("work_item_types.ee.project.custom")}
            </span>
          )}
        </div>
      </section>
      <section className="mt-6">
        <h4 className="text-body-sm-medium">{t("work_item_types.ee.project.assigned")}</h4>
        <ul className="mt-2 flex flex-col divide-y divide-subtle">
          {[...assigned]
            // oxlint-disable-next-line unicorn/no-array-sort -- copy; TS lib lacks toSorted
            .sort((a, b) => b.level - a.level || a.name.localeCompare(b.name))
            .map((type) => (
              <li key={type.id} className="flex items-center gap-3 py-2">
                <Logo logo={type.logo_props} size={16} type="lucide" />
                <span className="flex-1 truncate text-body-xs-regular">{typeName(type)}</span>
                {type.is_project_default ? (
                  <span className="text-body-xs-regular text-tertiary">
                    {t("work_item_types.ee.project.default_badge")}
                  </span>
                ) : (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={t("work_item_types.settings.set_as_default")}
                      onClick={() => run(() => store.setDefault(workspaceSlug, projectId, type.id))}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={t("work_item_types.ee.project.unassign")}
                      onClick={() => run(() => store.unassign(workspaceSlug, projectId, type.id))}
                    />
                  </>
                )}
              </li>
            ))}
        </ul>
      </section>
      {available.length > 0 && (
        <section className="mt-6">
          <h4 className="text-body-sm-medium">{t("work_item_types.ee.project.available")}</h4>
          <ul className="mt-2 flex flex-col divide-y divide-subtle">
            {available.map((type) => (
              <li key={type.id} className="flex items-center gap-3 py-2">
                <Logo logo={type.logo_props} size={16} type="lucide" />
                <span className="flex-1 truncate text-body-xs-regular">{typeName(type)}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label={t("work_item_types.ee.project.assign")}
                  onClick={() => run(() => store.assign(workspaceSlug, projectId, type.id))}
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </SettingsContentWrapper>
  );
}

export default observer(ProjectWorkItemTypesPage);
