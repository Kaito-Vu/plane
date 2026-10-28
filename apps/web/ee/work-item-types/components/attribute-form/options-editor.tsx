import { useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { useTranslation } from "@plane/i18n";
import type { TAttributeOption } from "../../types";
import { runWithToast } from "./helpers";
import type { TAttributeApi } from "./helpers";

type Props = {
  attributeId: string;
  options: TAttributeOption[];
  api: TAttributeApi;
  onChanged: () => Promise<unknown>;
  disabled?: boolean;
};

/** Options of a select / multi_select attribute or template. Delete is soft (is_active=false) server side. */
export function AttributeOptionsEditor({ attributeId, options, api, onChanged, disabled }: Props) {
  const { t } = useTranslation();
  const [newName, setNewName] = useState("");
  const active = options.filter((o) => o.is_active).toSorted((a, b) => a.sort_order - b.sort_order);

  const run = async (fn: () => Promise<unknown>) => {
    if (await runWithToast(t, fn)) await onChanged();
  };

  const add = async () => {
    const name = newName.trim();
    if (!name) return;
    await run(() => api.createOption(attributeId, { name }));
    setNewName("");
  };

  return (
    <div className="flex flex-col gap-2">
      {active.map((o) => (
        <div key={o.id} className="flex items-center gap-2">
          <Input
            size="md"
            defaultValue={o.name}
            disabled={disabled}
            aria-label={t("agile_attributes.options.name")}
            onBlur={(e) => {
              const name = e.target.value.trim();
              if (name && name !== o.name) void run(() => api.updateOption(attributeId, o.id, { name }));
            }}
          />
          <label className="flex items-center gap-1 text-12 whitespace-nowrap text-secondary">
            <input
              type="radio"
              name={`default-${attributeId}`}
              checked={o.is_default}
              disabled={disabled}
              onChange={() => void run(() => api.updateOption(attributeId, o.id, { is_default: true }))}
            />
            {t("agile_attributes.options.default")}
          </label>
          <Button
            stretch="auto"
            variant="ghost"
            size="sm"
            disabled={disabled}
            label={t("agile_attributes.actions.delete")}
            onClick={() => void run(() => api.deleteOption(attributeId, o.id))}
          />
        </div>
      ))}
      {!disabled && (
        <div className="flex items-center gap-2">
          <Input
            size="md"
            value={newName}
            placeholder={t("agile_attributes.options.add_placeholder")}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void add();
              }
            }}
          />
          <Button
            stretch="auto"
            variant="secondary"
            size="sm"
            label={t("agile_attributes.options.add")}
            onClick={() => void add()}
          />
        </div>
      )}
    </div>
  );
}
