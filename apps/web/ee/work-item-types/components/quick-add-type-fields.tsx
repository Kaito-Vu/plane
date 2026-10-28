import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import type { Control } from "react-hook-form";
import { Controller, useWatch } from "react-hook-form";
import type { ISearchIssueResponse, TIssue } from "@plane/types";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import { ParentPicker } from "./parent-picker";
import { TypeSelector } from "./type-selector";

type TProps = { projectId: string; control: Control<TIssue> };

/** Compact type + parent selector for inline quick-add rows (list/kanban/spreadsheet/cycle/module). */
export const QuickAddTypeFields = observer(function QuickAddTypeFields({ projectId, control }: TProps) {
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  const { getTypeKey, getTypeId } = useAttributes();
  const [parent, setParent] = useState<ISearchIssueResponse | null>(null);
  useEnsureProjectTypes(slug, projectId);
  const typeKey = getTypeKey(projectId, useWatch({ control, name: "type_id" }));
  return (
    <div className="flex flex-wrap items-start gap-3 px-3 py-2">
      <Controller
        control={control}
        name="type_id"
        render={({ field }) => (
          <TypeSelector compact value={typeKey} onChange={(k) => field.onChange(getTypeId(projectId, k) ?? null)} />
        )}
      />
      {typeKey && (
        <div className="min-w-60 flex-1">
          <Controller
            control={control}
            name="parent_id"
            render={({ field }) => (
              <ParentPicker
                workspaceSlug={slug}
                projectId={projectId}
                typeKey={typeKey}
                value={field.value ? parent : null}
                onChange={(issue) => {
                  setParent(issue);
                  field.onChange(issue?.id ?? null);
                }}
              />
            )}
          />
        </div>
      )}
    </div>
  );
});

/** Returns an i18n error key when a quick-add payload breaks the type/parent rules, else undefined. */
export const useQuickAddTypeValidation = () => {
  const { typeIdsByProject, getTypeKey } = useAttributes();
  return (projectId: string, data: Partial<TIssue>): string | undefined => {
    if (!typeIdsByProject[projectId]) return undefined; // types unknown: backend decides
    const key = getTypeKey(projectId, data.type_id);
    if (!key) return "agile_work_item.errors.type_required";
    if (key !== "epic" && !data.parent_id) return "agile_work_item.errors.parent_required";
    return undefined;
  };
};
