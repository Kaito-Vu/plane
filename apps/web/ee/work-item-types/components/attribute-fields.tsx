import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import { useAttributes } from "../hooks/use-attributes";
import type { TAttribute, TAttributeValues, TWorkItemTypeKey } from "../types";
import { AttributeValueEditor } from "./attribute-form/value-editor";

type TProps = {
  projectId: string;
  typeKey: TWorkItemTypeKey;
  values: TAttributeValues;
  onChange: (attributeId: string, value: unknown) => void;
  /** attribute id -> i18n key */
  errors?: Record<string, unknown>;
  disabled?: boolean;
};

export const isEmptyValue = (v: unknown) => v == null || v === "" || (Array.isArray(v) && v.length === 0);

/** Required active attributes of the type whose value is empty. */
export const missingRequired = (attrs: TAttribute[], values: TAttributeValues) =>
  attrs.filter((a) => a.is_required && a.field_type !== "boolean" && isEmptyValue(values[a.id]));

/** System + custom attribute editors of the chosen type (core fields stay in the default properties). */
export const AttributeFields = observer(function AttributeFields(props: TProps) {
  const { projectId, typeKey, values, onChange, errors = {}, disabled = false } = props;
  const { t } = useTranslation();
  const { getAttributesByType } = useAttributes();
  const attrs = getAttributesByType(projectId, typeKey);
  if (attrs.length === 0) return null;
  return (
    <fieldset disabled={disabled} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {attrs.map((a) => {
        const id = `attr-${a.id}`;
        const error = errors[a.id];
        return (
          <div key={a.id} className="flex flex-col gap-1">
            <label htmlFor={id} className="text-12 text-secondary">
              {a.name}
              {a.is_required && <span className="text-danger-primary"> *</span>}
            </label>
            <AttributeValueEditor
              id={id}
              fieldType={a.field_type}
              options={a.options}
              value={values[a.id] ?? null}
              onChange={(v) => onChange(a.id, v)}
            />
            {typeof error === "string" && <span className="text-11 text-danger-primary">{t(error)}</span>}
          </div>
        );
      })}
    </fieldset>
  );
});
