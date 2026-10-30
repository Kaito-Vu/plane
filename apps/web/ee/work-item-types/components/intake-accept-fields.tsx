import { observer } from "mobx-react";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import type { TWorkItemTypeKey } from "../types";
import { TypeSelector } from "./type-selector";

const INTAKE_TYPES: TWorkItemTypeKey[] = ["bug", "user_story"];

/** Intake create form: Bug (default, also the backend default) or User Story. Parent and required
 * attributes are not asked here; the accept modal (type-aware issue form) enforces them. */
export const IntakeTypeField = observer(function IntakeTypeField(props: {
  workspaceSlug: string;
  projectId: string;
  typeId: string | null | undefined;
  onChange: (typeId: string) => void;
}) {
  const { workspaceSlug, projectId, typeId, onChange } = props;
  const { getTypeKey, getTypeId } = useAttributes();
  useEnsureProjectTypes(workspaceSlug, projectId);
  if (!getTypeId(projectId, "bug")) return null;
  return (
    <TypeSelector
      compact
      allowed={INTAKE_TYPES}
      value={getTypeKey(projectId, typeId) ?? "bug"}
      onChange={(key) => {
        const id = getTypeId(projectId, key);
        if (id) onChange(id);
      }}
    />
  );
});
