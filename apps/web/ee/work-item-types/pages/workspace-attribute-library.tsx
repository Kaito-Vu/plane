import { useCallback, useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsPageHeader } from "@/components/settings/page-header";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { runWithToast } from "../components/attribute-form/helpers";
import type { TAttributeApi } from "../components/attribute-form/helpers";
import { AttributeSettingsView } from "../components/attribute-settings-view";
import { AttributeService } from "../services/attribute.service";
import type { TAttributeTemplate, TWorkItemTypeKey } from "../types";

const service = new AttributeService();

function WorkspaceAttributeLibraryPage() {
  const { workspaceSlug = "" } = useParams<{ workspaceSlug: string }>();
  const { t } = useTranslation();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { joinedProjectIds, workspaceProjectIds } = useProject();
  const [templates, setTemplates] = useState<TAttributeTemplate[]>([]);
  const [typeIds, setTypeIds] = useState<Partial<Record<TWorkItemTypeKey, string>>>({});
  const [typeKey, setTypeKey] = useState<TWorkItemTypeKey>("user_story");

  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  // Agile IssueTypes are workspace-level rows shared by every project, so any project's type list
  // yields the workspace ids. ponytail: no workspace-level types endpoint; add one if a workspace has no projects.
  const anyProjectId = joinedProjectIds[0] ?? workspaceProjectIds?.[0];

  const reload = useCallback(async () => setTemplates(await service.getTemplates(workspaceSlug)), [workspaceSlug]);

  useEffect(() => {
    if (!workspaceSlug || !isAdmin) return;
    void runWithToast(t, reload);
  }, [workspaceSlug, isAdmin, reload, t]);

  useEffect(() => {
    if (!workspaceSlug || !anyProjectId || !isAdmin) return;
    void runWithToast(t, async () => {
      const list = await service.fetchProjectTypes(workspaceSlug, anyProjectId);
      setTypeIds(Object.fromEntries(list.map((x) => [x.key, x.id])));
    });
  }, [workspaceSlug, anyProjectId, isAdmin, t]);

  const api = useMemo<TAttributeApi>(
    () => ({
      create: (data) => service.createTemplate(workspaceSlug, data),
      update: (id, data) => service.updateTemplate(workspaceSlug, id, data),
      remove: (id) => service.deleteTemplate(workspaceSlug, id),
      // the template reorder endpoint takes ids only; sort_order is global but listed per type
      reorder: (ids) => service.reorderTemplates(workspaceSlug, ids),
      createOption: (id, data) => service.createTemplateOption(workspaceSlug, id, data),
      updateOption: (id, optionId, data) => service.updateTemplateOption(workspaceSlug, id, optionId, data),
      deleteOption: (id, optionId) => service.deleteTemplateOption(workspaceSlug, id, optionId),
    }),
    [workspaceSlug]
  );

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" className="h-auto" />;

  return (
    <SettingsContentWrapper
      header={
        <SettingsPageHeader
          leftItem={<span className="text-13 font-medium">{t("agile_attributes.library_title")}</span>}
        />
      }
    >
      <PageHead title={t("agile_attributes.library_title")} />
      <div className="flex flex-col gap-4 p-4">
        <p className="text-13 text-secondary">{t("agile_attributes.library_description")}</p>
        {anyProjectId ? (
          <AttributeSettingsView
            typeIds={typeIds}
            typeKey={typeKey}
            onTypeChange={setTypeKey}
            items={templates}
            api={api}
            reload={reload}
            canEdit={isAdmin}
          />
        ) : (
          <p className="text-13 text-tertiary">{t("agile_attributes.library_no_project")}</p>
        )}
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(WorkspaceAttributeLibraryPage);
