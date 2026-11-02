import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { useFormContext } from "react-hook-form";
import type { TIssue } from "@plane/types";
import { useIssueModal } from "@/hooks/context/use-issue-modal";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { childTypesOf, TYPE_KEYS } from "../constants";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import { AttributeService } from "../services/attribute.service";
import type { TWorkItemTypeKey } from "../types";
import { PARENT_FIELD, TYPE_FIELD } from "../work-item-errors";
import { AttributeFields } from "./attribute-fields";
import { ParentPicker } from "./parent-picker";
import { TypeSelector } from "./type-selector";

const service = new AttributeService();

type TProps = { issueId?: string };

/** Type → parent → attributes block of the issue modal (must live inside the form's FormProvider). */
export const WorkItemTypeFormFields = observer(function WorkItemTypeFormFields({ issueId }: TProps) {
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  const { watch, setValue } = useFormContext<TIssue>();
  const {
    selectedParentIssue,
    setSelectedParentIssue,
    issuePropertyValues,
    setIssuePropertyValues,
    issuePropertyValueErrors: errors,
    setIssuePropertyValueErrors,
  } = useIssueModal();
  const { getTypeKey, getTypeId } = useAttributes();
  const {
    issue: { getIssueById },
  } = useIssueDetail();

  const projectId = watch("project_id");
  const parentId = watch("parent_id");
  const typeKey = getTypeKey(projectId, watch("type_id"));
  useEnsureProjectTypes(slug, projectId);

  // edit: load current values
  useEffect(() => {
    if (!issueId || !projectId || !slug) return;
    service.getAttributeValues(slug, projectId, issueId).then(setIssuePropertyValues).catch(console.error);
  }, [issueId, projectId, slug, setIssuePropertyValues]);

  if (!projectId) return null;

  const parentTypeId = (parentId && getIssueById(parentId)?.type_id) || selectedParentIssue?.type_id;
  const parentKey = getTypeKey(projectId, parentTypeId);
  // sub-issue creation: only child types valid for the parent's type
  const allowed: TWorkItemTypeKey[] = !issueId && parentKey ? childTypesOf(parentKey) : TYPE_KEYS;
  const fieldError = (k: string) => (typeof errors[k] === "string" ? errors[k] : undefined);
  const clearError = (k: string) => setIssuePropertyValueErrors((prev) => ({ ...prev, [k]: undefined }));

  return (
    <div className="flex flex-col gap-3">
      <TypeSelector
        value={typeKey}
        allowed={allowed}
        disabled={!!issueId}
        error={fieldError(TYPE_FIELD)}
        onChange={(k) => {
          setValue("type_id", getTypeId(projectId, k) ?? null, { shouldDirty: true });
          clearError(TYPE_FIELD);
          clearError(PARENT_FIELD); // parent requirement depends on the type
        }}
      />
      {typeKey && (
        <>
          <ParentPicker
            workspaceSlug={slug}
            projectId={projectId}
            typeKey={typeKey}
            issueId={issueId}
            value={parentId ? selectedParentIssue : null}
            error={fieldError(PARENT_FIELD)}
            onChange={(issue) => {
              setValue("parent_id", issue?.id ?? null, { shouldDirty: true });
              setSelectedParentIssue(issue);
              clearError(PARENT_FIELD);
            }}
          />
          <AttributeFields
            projectId={projectId}
            typeKey={typeKey}
            values={issuePropertyValues}
            errors={errors}
            onChange={(id, v) => {
              setIssuePropertyValues((prev) => ({ ...prev, [id]: v }));
              clearError(id);
            }}
          />
        </>
      )}
    </div>
  );
});
