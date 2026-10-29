import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { BorderedInput as Input } from "./attribute-form/bordered-input";
import { useTranslation } from "@plane/i18n";
import type { ISearchIssueResponse } from "@plane/types";
import useDebounce from "@/hooks/use-debounce";
import { ProjectService } from "@/services/project";
import { useAttributes } from "../hooks/use-attributes";
import type { TWorkItemTypeKey } from "../types";
import { TypeBadge } from "./type-badge";

const projectService = new ProjectService();

type TProps = {
  workspaceSlug: string;
  projectId: string;
  /** Type of the item being created; parents are limited to allowedParentTypes(typeKey). */
  typeKey: TWorkItemTypeKey;
  /** Issue being edited (excluded from results). */
  issueId?: string;
  value: ISearchIssueResponse | null;
  onChange: (issue: ISearchIssueResponse | null) => void;
  error?: string;
  disabled?: boolean;
};

export const ParentPicker = observer(function ParentPicker(props: TProps) {
  const { workspaceSlug, projectId, typeKey, issueId, value, onChange, error, disabled = false } = props;
  const { t } = useTranslation();
  const { allowedParentTypes, getTypeKey } = useAttributes();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<ISearchIssueResponse[]>([]);
  const debounced = useDebounce(search, 400);
  const allowed = allowedParentTypes(typeKey);
  const optional = typeKey === "epic";

  useEffect(() => {
    if (!open) return;
    let alive = true;
    projectService
      .projectIssuesSearch(workspaceSlug, projectId, {
        search: debounced,
        parent: true,
        issue_id: issueId,
        workspace_search: false,
      })
      .then((res) => {
        // same project only, and only types allowed as parent of typeKey
        const matches = res.filter((i) => {
          const k = getTypeKey(projectId, i.type_id);
          return i.project_id === projectId && !!k && allowed.includes(k);
        });
        if (alive) setResults(matches);
        return matches;
      })
      .catch(() => alive && setResults([]));
    return () => {
      alive = false;
    };
    // allowed derives from typeKey
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [open, debounced, workspaceSlug, projectId, typeKey, issueId, getTypeKey]);

  return (
    <div className="flex flex-col gap-1">
      <span className="text-12 text-secondary">
        {t("agile_work_item.parent")}
        {!optional && <span className="text-danger-primary"> *</span>}
      </span>
      {value ? (
        <div className="flex items-center gap-2 text-13">
          <TypeBadge projectId={projectId} typeId={value.type_id} />
          <span className="truncate">
            {value.project__identifier}-{value.sequence_id} {value.name}
          </span>
          {!disabled && (
            <button type="button" className="text-12 text-tertiary hover:text-primary" onClick={() => onChange(null)}>
              {t("agile_work_item.clear")}
            </button>
          )}
        </div>
      ) : (
        <div className="relative">
          <Input
            size="md"
            value={search}
            disabled={disabled}
            placeholder={t("agile_work_item.parent_search", {
              types: allowed.map((k) => t(`agile_attributes.types.${k}`)).join(", "),
            })}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onChange={(e) => setSearch(e.target.value)}
          />
          {open && (
            <ul className="shadow-md absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-subtle bg-surface-1 py-1">
              {results.length === 0 ? (
                <li className="px-2 py-1 text-12 text-tertiary">{t("agile_work_item.no_parent_found")}</li>
              ) : (
                results.map((i) => (
                  <li key={i.id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 px-2 py-1 text-left text-13 hover:bg-layer-1-hover"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        onChange(i);
                        setSearch("");
                        setOpen(false);
                      }}
                    >
                      <TypeBadge projectId={projectId} typeId={i.type_id} />
                      <span className="shrink-0 text-tertiary">
                        {i.project__identifier}-{i.sequence_id}
                      </span>
                      <span className="truncate">{i.name}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          )}
        </div>
      )}
      {error && <span className="text-11 text-danger-primary">{t(error)}</span>}
    </div>
  );
});
