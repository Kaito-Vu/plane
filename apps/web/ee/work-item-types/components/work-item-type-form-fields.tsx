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
import type { TAttribute, TWorkItemTypeKey } from "../types";
import { PARENT_FIELD, TYPE_FIELD } from "../work-item-errors";
import { AttributeFields } from "./attribute-fields";
import { ParentPicker } from "./parent-picker";
import { TypeSelector } from "./type-selector";

const service = new AttributeService();

type TProps = {
  issueId?: string;
  /** "type": the type selector (top of the form); "details": type attributes, then parent (bottom). */
  part: "type" | "details";
};

// story points belong to user stories only; spent time / remaining work are tracked after creation
const hideAttribute = (typeKey: TWorkItemTypeKey, creating: boolean) => (a: TAttribute) =>
  (a.system_key === "story_points" && typeKey !== "user_story") ||
  (creating && (a.system_key === "spent_time" || a.system_key === "remaining_work"));

/** Type / attributes / parent blocks of the issue modal (must live inside the form's FormProvider). */
export const WorkItemTypeFormFields = observer(function WorkItemTypeFormFields({ issueId, part }: TProps) {
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
  const { getTypeKey, getTypeId, getAttributesByType } = useAttributes();
  const {
    issue: { getIssueById },
  } = useIssueDetail();

  const projectId = watch("project_id");
  const parentId = watch("parent_id");
  const typeKey = getTypeKey(projectId, watch("type_id"));
  useEnsureProjectTypes(slug, projectId);

  // edit: load current values
  useEffect(() => {
    if (part !== "details" || !issueId || !projectId || !slug) return;
    let alive = true;
    service
      .getAttributeValues(slug, projectId, issueId)
      .then((v) => alive && setIssuePropertyValues(v))
      .catch(console.error);
    return () => {
      alive = false;
    };
  }, [part, issueId, projectId, slug, setIssuePropertyValues]);

  if (!projectId) return null;

  const parentTypeId = (parentId && getIssueById(parentId)?.type_id) || selectedParentIssue?.type_id;
  const parentKey = getTypeKey(projectId, parentTypeId);
  // sub-issue creation: only child types valid for the parent's type
  const allowed: TWorkItemTypeKey[] = !issueId && parentKey ? childTypesOf(parentKey) : TYPE_KEYS;
  const fieldError = (k: string) => (typeof errors[k] === "string" ? errors[k] : undefined);
  const clearError = (k: string) => setIssuePropertyValueErrors((prev) => ({ ...prev, [k]: undefined }));

  if (part === "type")
    return (
      <TypeSelector
        value={typeKey}
        allowed={allowed}
        disabled={!!issueId}
        error={fieldError(TYPE_FIELD)}
        onChange={(k) => {
          setValue("type_id", getTypeId(projectId, k) ?? null, { shouldDirty: true });
          setIssuePropertyValues({}); // values belong to the previous type's attributes; the API rejects them
          clearError(TYPE_FIELD);
          clearError(PARENT_FIELD); // parent requirement depends on the type
        }}
      />
    );

  if (!typeKey) return null;
  return (
    <div className="flex flex-col gap-3">
      <AttributeFields
        projectId={projectId}
        typeKey={typeKey}
        values={issuePropertyValues}
        errors={errors}
        hide={hideAttribute(typeKey, !issueId)}
        onChange={(id, v) => {
          setIssuePropertyValues((prev) => {
            const next = { ...prev, [id]: v };
            // new work item: remaining work starts equal to the original estimate
            if (!issueId) {
              const attrs = getAttributesByType(projectId, typeKey);
              const est = attrs.find((a) => a.system_key === "original_estimate");
              const rem = attrs.find((a) => a.system_key === "remaining_work");
              if (est && rem && est.id === id) next[rem.id] = v;
            }
            return next;
          });
          clearError(id);
        }}
      />
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
    </div>
  );
});
