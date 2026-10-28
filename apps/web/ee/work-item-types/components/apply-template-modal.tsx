import { useEffect, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { useTranslation } from "@plane/i18n";
import { AttributeService } from "../services/attribute.service";
import type { TAttributeTemplate, TWorkItemTypeKey } from "../types";
import { runWithToast } from "./attribute-form/helpers";

const service = new AttributeService();
const SELECT_CLASS = "w-full rounded-md border border-subtle bg-surface-1 px-2 py-1.5 text-13";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  projectId: string;
  typeIds: Partial<Record<TWorkItemTypeKey, string>>;
  defaultTypeKey: TWorkItemTypeKey;
  onApplied: () => Promise<unknown>;
};

/** Copies a workspace template into the project; the copy is independent of later template edits. */
export function ApplyTemplateModal(props: Props) {
  const { isOpen, onClose, workspaceSlug, projectId, typeIds, defaultTypeKey, onApplied } = props;
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<TAttributeTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [typeKey, setTypeKey] = useState<TWorkItemTypeKey>(defaultTypeKey);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setTypeKey(defaultTypeKey);
    setTemplateId("");
    // the list endpoint is workspace-admin only; non admins just see an empty picker + toast
    void runWithToast(t, async () => setTemplates(await service.getTemplates(workspaceSlug)));
  }, [isOpen, workspaceSlug, defaultTypeKey, t]);

  // a template is defined for one type; only offer templates of the chosen type
  const typeId = typeIds[typeKey];
  const choices = templates.filter((tpl) => tpl.issue_type === typeId && tpl.is_active);

  const apply = async () => {
    if (!templateId || !typeId) return;
    setSaving(true);
    const ok = await runWithToast(t, () => service.applyTemplate(workspaceSlug, projectId, templateId, typeId));
    setSaving(false);
    if (!ok) return;
    await onApplied();
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="md">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("agile_attributes.apply_template.title")}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-3 text-13">
              <label className="flex flex-col gap-1">
                {t("agile_attributes.type_select")}
                <select
                  className={SELECT_CLASS}
                  value={typeKey}
                  onChange={(e) => {
                    setTypeKey(e.target.value as TWorkItemTypeKey);
                    setTemplateId("");
                  }}
                >
                  {(Object.keys(typeIds) as TWorkItemTypeKey[]).map((k) => (
                    <option key={k} value={k}>
                      {t(`agile_attributes.types.${k}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                {t("agile_attributes.apply_template.template")}
                <select className={SELECT_CLASS} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                  <option value="">—</option>
                  {choices.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.name} ({t(`agile_attributes.field_types.${tpl.field_type}`)})
                    </option>
                  ))}
                </select>
              </label>
              <p className="text-12 text-tertiary">{t("agile_attributes.apply_template.hint")}</p>
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" label={t("agile_attributes.actions.cancel")} onClick={onClose} />
          <Button
            variant="primary"
            size="md"
            disabled={saving || !templateId}
            label={t("agile_attributes.apply_template.apply")}
            onClick={() => void apply()}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
