import { useCallback, useState } from "react";
import { useTranslation } from "@plane/i18n";
import { setToast } from "@plane/blocks/toast";
import type { TIssuePropertyValueErrors, TIssuePropertyValues } from "@plane/types";
import type { TPropertyValuesValidationProps } from "@/components/issues/issue-modal/context";
import { missingRequired } from "../components/attribute-fields";
import { PARENT_FIELD, TYPE_FIELD } from "../work-item-errors";
import { useAttributes } from "./use-attributes";

/** EE implementation of the issue-modal context slots for work item types (spread into the core provider). */
export const useWorkItemTypeModalState = () => {
  const { t } = useTranslation();
  const { typeIdsByProject, getTypeKey, getAttributesByType } = useAttributes();
  const [issuePropertyValues, setIssuePropertyValues] = useState<TIssuePropertyValues>({});
  const [issuePropertyValueErrors, setIssuePropertyValueErrors] = useState<TIssuePropertyValueErrors>({});

  // Client-side check before submit: type chosen, parent rule, required attributes.
  const handlePropertyValuesValidation = useCallback(
    ({ projectId, watch }: TPropertyValuesValidationProps) => {
      // types not loaded for this project (e.g. no agile types): leave validation to the backend
      if (!projectId || !typeIdsByProject[projectId]) return true;
      const errors: Record<string, string> = {};
      const key = getTypeKey(projectId, watch("type_id"));
      if (!key) errors[TYPE_FIELD] = "agile_work_item.errors.type_required";
      else {
        if (key !== "epic" && !watch("parent_id")) errors[PARENT_FIELD] = "agile_work_item.errors.parent_required";
        for (const a of missingRequired(getAttributesByType(projectId, key), issuePropertyValues))
          errors[a.id] = "agile_work_item.errors.field_required";
      }
      setIssuePropertyValueErrors(errors);
      const ok = Object.keys(errors).length === 0;
      if (!ok) setToast({ type: "error", title: t("error"), message: t("agile_work_item.errors.fix_fields") });
      return ok;
    },
    [t, typeIdsByProject, getTypeKey, getAttributesByType, issuePropertyValues]
  );

  // Values travel in the create/update payload (attribute_values); after a save just reset for "create more".
  const handleCreateUpdatePropertyValues = useCallback(async () => {
    setIssuePropertyValues({});
    setIssuePropertyValueErrors({});
  }, []);

  return {
    issuePropertyValues,
    setIssuePropertyValues,
    issuePropertyValueErrors,
    setIssuePropertyValueErrors,
    handlePropertyValuesValidation,
    handleCreateUpdatePropertyValues,
  };
};
