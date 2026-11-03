import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import { AttributeService } from "../services/attribute.service";
import type { TAttributeValues } from "../types";
import { workItemErrorMessage, workItemFieldErrors } from "../work-item-errors";
import { AttributeFields, missingRequired } from "./attribute-fields";
import { TypeKeyBadge } from "./type-badge";

const service = new AttributeService();

type TProps = { workspaceSlug: string; projectId: string; issueId: string; disabled: boolean };

/** Detail sidebar: read-only type + editable attribute values of the issue's type. */
export const IssueAttributesPanel = observer(function IssueAttributesPanel(props: TProps) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const { t } = useTranslation();
  const { getTypeKey, getAttributesByType, setIssueValues } = useAttributes();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const [saved, setSaved] = useState<TAttributeValues>({});
  const [values, setValues] = useState<TAttributeValues>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  useEnsureProjectTypes(workspaceSlug, projectId);

  useEffect(() => {
    // reset + stale guard: a late response for the previous issue must never be saved onto this one
    let alive = true;
    setSaved({});
    setValues({});
    setErrors({});
    service
      .getAttributeValues(workspaceSlug, projectId, issueId)
      .then((v) => {
        if (!alive) return v;
        setSaved(v);
        setValues(v);
        return v;
      })
      .catch(console.error);
    return () => {
      alive = false;
    };
  }, [workspaceSlug, projectId, issueId]);

  const typeKey = getTypeKey(projectId, getIssueById(issueId)?.type_id);
  if (!typeKey) return null;
  const dirty = JSON.stringify(saved) !== JSON.stringify(values);

  const save = async () => {
    const missing = missingRequired(getAttributesByType(projectId, typeKey), values);
    if (missing.length > 0) {
      setErrors(Object.fromEntries(missing.map((a) => [a.id, "agile_work_item.errors.field_required"])));
      return;
    }
    setSaving(true);
    try {
      await service.updateAttributeValues(workspaceSlug, projectId, issueId, values);
      setSaved(values);
      setIssueValues(issueId, values); // refresh list/spreadsheet attribute columns
      setErrors({});
    } catch (err) {
      setErrors(workItemFieldErrors(err));
      setToast({
        type: "error",
        title: t("error"),
        message: workItemErrorMessage(t, err) ?? t("issue_could_not_be_updated"),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-13">
        <span className="text-secondary">{t("agile_work_item.type")}</span>
        <TypeKeyBadge typeKey={typeKey} />
      </div>
      <AttributeFields
        projectId={projectId}
        typeKey={typeKey}
        values={values}
        errors={errors}
        disabled={disabled}
        onChange={(id, v) => setValues((prev) => ({ ...prev, [id]: v }))}
      />
      {dirty && !disabled && (
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" stretch="auto" label={t("cancel")} onClick={() => setValues(saved)} />
          <Button variant="primary" size="sm" stretch="auto" label={t("save")} loading={saving} onClick={save} />
        </div>
      )}
    </div>
  );
});
