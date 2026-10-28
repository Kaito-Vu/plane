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
import { Input } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { useTranslation } from "@plane/i18n";
import type { TAttributeFieldType } from "../../types";
import { runWithToast } from "./helpers";
import type { TAttributeApi, TAttributeLike } from "./helpers";
import { AttributeOptionsEditor } from "./options-editor";
import { AttributeValueEditor, FIELD_TYPES, OPTION_FIELD_TYPES } from "./value-editor";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  issueTypeId: string;
  /** undefined = create */
  attribute: TAttributeLike | undefined;
  api: TAttributeApi;
  onChanged: () => Promise<unknown>;
};

type TForm = Pick<TAttributeLike, "name" | "description" | "field_type" | "is_required" | "default_value">;

const EMPTY: TForm = { name: "", description: "", field_type: "text", is_required: false, default_value: null };

export function AttributeFormModal({ isOpen, onClose, issueTypeId, attribute, api, onChanged }: Props) {
  const { t } = useTranslation();
  const [form, setForm] = useState<TForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const isSystem = !!attribute?.is_system;
  const set = <K extends keyof TForm>(k: K, v: TForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!isOpen) return;
    setForm(
      attribute
        ? {
            name: attribute.name,
            description: attribute.description,
            field_type: attribute.field_type,
            is_required: attribute.is_required,
            default_value: attribute.default_value,
          }
        : EMPTY
    );
    // reset only when opening / switching attribute, not when options reload
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, attribute?.id]);

  const submit = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    // system attributes: the backend accepts is_required only
    const ok = await runWithToast(t, () =>
      attribute
        ? api.update(attribute.id, isSystem ? { is_required: form.is_required } : form)
        : api.create({ ...form, issue_type: issueTypeId })
    );
    setSaving(false);
    if (!ok) return;
    await onChanged();
    onClose();
  };

  const optionsEditable = !isSystem || attribute?.system_key === "project_phase";

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="md">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>
                {t(attribute ? "agile_attributes.form.edit_title" : "agile_attributes.form.create_title")}
              </DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-13">
                {t("agile_attributes.form.name")}
                <Input size="md" value={form.name} disabled={isSystem} onChange={(e) => set("name", e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-13">
                {t("agile_attributes.form.description")}
                <Input
                  size="md"
                  value={form.description}
                  disabled={isSystem}
                  onChange={(e) => set("description", e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-13">
                {t("agile_attributes.form.field_type")}
                <select
                  className="w-full rounded-md border border-subtle bg-surface-1 px-2 py-1.5 text-13"
                  value={form.field_type}
                  disabled={isSystem}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, field_type: e.target.value as TAttributeFieldType, default_value: null }))
                  }
                >
                  {FIELD_TYPES.map((ft) => (
                    <option key={ft} value={ft}>
                      {t(`agile_attributes.field_types.${ft}`)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-center justify-between text-13">
                {t("agile_attributes.form.is_required")}
                <Switch size="md" checked={form.is_required} onCheckedChange={(v: boolean) => set("is_required", v)} />
              </div>
              {!isSystem && (
                <div className="flex flex-col gap-1 text-13">
                  {t("agile_attributes.form.default_value")}
                  <AttributeValueEditor
                    fieldType={form.field_type}
                    options={attribute?.options ?? []}
                    value={form.default_value}
                    onChange={(v) => set("default_value", v)}
                  />
                </div>
              )}
              {OPTION_FIELD_TYPES.includes(form.field_type) && (
                <div className="flex flex-col gap-1 text-13">
                  {t("agile_attributes.options.title")}
                  {attribute && attribute.field_type === form.field_type ? (
                    <AttributeOptionsEditor
                      attributeId={attribute.id}
                      options={attribute.options}
                      api={api}
                      onChanged={onChanged}
                      disabled={!optionsEditable}
                    />
                  ) : (
                    <p className="text-12 text-tertiary">{t("agile_attributes.options.save_first")}</p>
                  )}
                </div>
              )}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button
            stretch="auto"
            variant="secondary"
            size="md"
            label={t("agile_attributes.actions.cancel")}
            onClick={onClose}
          />
          <Button
            stretch="auto"
            variant="primary"
            size="md"
            disabled={saving || !form.name.trim()}
            label={t("agile_attributes.actions.save")}
            onClick={() => void submit()}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
