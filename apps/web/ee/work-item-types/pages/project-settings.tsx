/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { CheckboxField } from "@makeplane/propel/components/checkbox-field";
import { RadioGroupField, RadioGroupFieldOption } from "@makeplane/propel/components/radio-group-field";
import { Switch } from "@makeplane/propel/components/switch";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TIssueTypeConflict, TProjectIssueType, TWorkItemProcess } from "@plane/types";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useUserPermissions } from "@/hooks/store/user";
import { ConfirmDialog } from "../components/confirm-dialog";
import { SettingsError, SettingsLoader } from "../components/settings-states";
import { useTypeName } from "../components/type-name";
import { useProjectWorkItemTypesQuery, useWorkItemTypes, useWorkspaceWorkItemTypesQuery } from "../hooks";
import { firstErrorMessage, levelMeaningKey } from "../rules";

const PROCESSES: TWorkItemProcess[] = ["scrum", "agile"];

type TPending =
  | { kind: "process"; process: TWorkItemProcess }
  | { kind: "disable" }
  | { kind: "unassign"; type: TProjectIssueType };

function ProjectWorkItemTypesPage() {
  const params = useParams();
  const workspaceSlug = params.workspaceSlug?.toString() ?? "";
  const projectId = params.projectId?.toString() ?? "";
  const { t } = useTranslation();
  const typeName = useTypeName();
  const store = useWorkItemTypes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const {
    config,
    error: configError,
    retry: retryConfig,
  } = useProjectWorkItemTypesQuery(isAdmin ? workspaceSlug : undefined, projectId, true);
  const {
    types: workspaceTypes,
    error: workspaceError,
    retry: retryWorkspace,
  } = useWorkspaceWorkItemTypesQuery(isAdmin ? workspaceSlug : undefined);
  const [pending, setPending] = useState<TPending | null>(null);
  const [migrate, setMigrate] = useState(false);
  const [blockedCount, setBlockedCount] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  const showError = (error: unknown, fallback = t("work_item_types.ee.project.action_failed")) =>
    setToast({
      type: "error",
      title: t("work_item_types.update.toast.error.title"),
      message: firstErrorMessage(error) ?? fallback,
    });
  // every action refetches the project; errors (409 in-use, 400 invalid) are shown verbatim from the server
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
    } catch (error) {
      showError(error);
    }
  };
  const ask = (next: TPending) => {
    setMigrate(false);
    setBlockedCount(null);
    setPending(next);
  };
  const close = () => setPending(null);

  const confirm = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending.kind === "process") await store.setProcess(workspaceSlug, projectId, pending.process, migrate);
      else if (pending.kind === "disable") await store.setEnabled(workspaceSlug, projectId, false);
      else await store.unassign(workspaceSlug, projectId, pending.type.id);
      close();
    } catch (error) {
      const conflict = error as TIssueTypeConflict | undefined;
      if (conflict?.code === "process_change_blocked")
        setBlockedCount(conflict.count ?? 0); // offer the "convert" checkbox
      else if (conflict?.code === "process_conflict")
        showError(error, t("work_item_types.ee.project.process_conflict"));
      else showError(error);
    } finally {
      setBusy(false);
    }
  };

  const assigned = config?.types ?? [];
  const assignedIds = new Set(assigned.map((type) => type.id));
  const available = (workspaceTypes ?? []).filter((type) => type.is_active && !assignedIds.has(type.id));
  const loadFailed = !!(configError || workspaceError);
  const processName = (process: TWorkItemProcess) => t(`work_item_types.ee.project.${process}`);

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
                onCheckedChange={(enabled) =>
                  enabled ? run(() => store.setEnabled(workspaceSlug, projectId, true)) : ask({ kind: "disable" })
                }
              />
              {t("work_item_types.ee.project.enabled")}
            </label>
          )
        }
      />
      {(!config || !workspaceTypes) &&
        (loadFailed ? (
          <SettingsError
            onRetry={() => {
              void retryConfig();
              void retryWorkspace();
            }}
          />
        ) : (
          <SettingsLoader />
        ))}
      {config && workspaceTypes && (
        <>
          <section className="mt-6 flex flex-col gap-2">
            {/* Base UI radio group: arrow-key roving focus, one tab stop; not interactive until config exists */}
            <RadioGroupField<string>
              name="process"
              label={t("work_item_types.ee.project.process")}
              size="md"
              density="comfortable"
              value={config.process ?? ""}
              onValueChange={(value) => {
                if (value !== config.process) ask({ kind: "process", process: value as TWorkItemProcess });
              }}
            >
              {PROCESSES.map((process) => (
                <RadioGroupFieldOption key={process} value={process} label={processName(process)} />
              ))}
            </RadioGroupField>
            {config.enabled && config.process === null && (
              <span className="text-body-xs-regular text-tertiary">{t("work_item_types.ee.project.custom")}</span>
            )}
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
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-body-xs-regular" title={typeName(type)}>
                        {typeName(type)}
                      </span>
                      <span className="text-body-xs-regular text-tertiary">
                        {t("work_item_types.ee.workspace.level")} {type.level} · {t(levelMeaningKey(type.level))}
                      </span>
                    </div>
                    {type.is_project_default ? (
                      <span
                        className="rounded-full bg-layer-2 px-2 py-0.5 text-body-xs-medium text-secondary"
                        title={t("work_item_types.ee.project.default_hint")}
                      >
                        {t("work_item_types.ee.project.default_badge")}
                        <span className="sr-only"> - {t("work_item_types.ee.project.default_hint")}</span>
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
                          onClick={() => ask({ kind: "unassign", type })}
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
                    <span className="flex-1 truncate text-body-xs-regular" title={typeName(type)}>
                      {typeName(type)}
                    </span>
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
        </>
      )}
      {pending?.kind === "process" && (
        <ConfirmDialog
          title={t("work_item_types.ee.project.confirm_process_title", { process: processName(pending.process) })}
          confirmLabel={t("work_item_types.ee.project.confirm_process_button")}
          busy={busy}
          onConfirm={confirm}
          onClose={close}
        >
          <p className="text-body-xs-regular text-secondary">
            {t("work_item_types.ee.project.confirm_process_description", { process: processName(pending.process) })}
          </p>
          {blockedCount !== null && (
            <p role="alert" className="mt-3 text-body-xs-regular text-danger-primary">
              {t("work_item_types.ee.project.process_blocked", { count: blockedCount })}
            </p>
          )}
          <div className="mt-3">
            <CheckboxField
              size="md"
              checked={migrate}
              onCheckedChange={(checked) => setMigrate(checked === true)}
              label={t("work_item_types.ee.project.migrate_label")}
            />
          </div>
        </ConfirmDialog>
      )}
      {pending?.kind === "disable" && (
        <ConfirmDialog
          title={t("work_item_types.ee.project.disable_title")}
          confirmLabel={t("work_item_types.ee.confirm")}
          busy={busy}
          onConfirm={confirm}
          onClose={close}
        >
          <p className="text-body-xs-regular text-secondary">{t("work_item_types.ee.project.disable_description")}</p>
        </ConfirmDialog>
      )}
      {pending?.kind === "unassign" && (
        <ConfirmDialog
          title={t("work_item_types.ee.project.unassign_title", { name: typeName(pending.type) })}
          confirmLabel={t("work_item_types.ee.project.unassign")}
          danger
          busy={busy}
          onConfirm={confirm}
          onClose={close}
        >
          <p className="text-body-xs-regular text-secondary">{t("work_item_types.ee.project.unassign_description")}</p>
        </ConfirmDialog>
      )}
    </SettingsContentWrapper>
  );
}

export default observer(ProjectWorkItemTypesPage);
