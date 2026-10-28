import { useCallback, useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsPageHeader } from "@/components/settings/page-header";
import { useUserPermissions } from "@/hooks/store/user";
import { ApplyTemplateModal } from "../components/apply-template-modal";
import { runWithToast } from "../components/attribute-form/helpers";
import type { TAttributeApi } from "../components/attribute-form/helpers";
import { AttributeSettingsView } from "../components/attribute-settings-view";
import { useAttributes } from "../hooks/use-attributes";
import { AttributeService } from "../services/attribute.service";
import type { TWorkItemTypeKey } from "../types";

const service = new AttributeService();

function ProjectAttributesPage() {
  const { workspaceSlug = "", projectId = "" } = useParams<{ workspaceSlug: string; projectId: string }>();
  const { t } = useTranslation();
  const { attributesByProject, typeIdsByProject, fetchProjectTypes, fetchProjectAttributes } = useAttributes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const [typeKey, setTypeKey] = useState<TWorkItemTypeKey>("user_story");
  const [applyOpen, setApplyOpen] = useState(false);

  const canView = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.PROJECT);
  const canEdit = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  const reload = useCallback(
    () => fetchProjectAttributes(workspaceSlug, projectId),
    [workspaceSlug, projectId, fetchProjectAttributes]
  );

  useEffect(() => {
    if (!workspaceSlug || !projectId) return;
    void runWithToast(t, () => Promise.all([fetchProjectTypes(workspaceSlug, projectId), reload()]));
  }, [workspaceSlug, projectId, fetchProjectTypes, reload, t]);

  const api = useMemo<TAttributeApi>(
    () => ({
      create: (data) => service.createAttribute(workspaceSlug, projectId, data),
      update: (id, data) => service.updateAttribute(workspaceSlug, projectId, id, data),
      remove: (id) => service.deleteAttribute(workspaceSlug, projectId, id),
      reorder: (ids, typeId) => service.reorderAttributes(workspaceSlug, projectId, ids, typeId),
      createOption: (id, data) => service.createOption(workspaceSlug, projectId, id, data),
      updateOption: (id, optionId, data) => service.updateOption(workspaceSlug, projectId, id, optionId, data),
      deleteOption: (id, optionId) => service.deleteOption(workspaceSlug, projectId, id, optionId),
    }),
    [workspaceSlug, projectId]
  );

  if (workspaceUserInfo && !canView) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  const typeIds = typeIdsByProject[projectId] ?? {};

  return (
    <SettingsContentWrapper
      header={
        <SettingsPageHeader leftItem={<span className="text-13 font-medium">{t("agile_attributes.title")}</span>} />
      }
    >
      <PageHead title={t("agile_attributes.title")} />
      <div className="flex flex-col gap-4 p-4">
        <p className="text-13 text-secondary">{t("agile_attributes.project_description")}</p>
        <AttributeSettingsView
          typeIds={typeIds}
          typeKey={typeKey}
          onTypeChange={setTypeKey}
          items={attributesByProject[projectId] ?? []}
          api={api}
          reload={reload}
          canEdit={canEdit}
          extraActions={
            <Button
              variant="secondary"
              size="md"
              label={t("agile_attributes.apply_template.open")}
              onClick={() => setApplyOpen(true)}
            />
          }
        />
      </div>
      <ApplyTemplateModal
        isOpen={applyOpen}
        onClose={() => setApplyOpen(false)}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        typeIds={typeIds}
        defaultTypeKey={typeKey}
        onApplied={reload}
      />
    </SettingsContentWrapper>
  );
}

export default observer(ProjectAttributesPage);
