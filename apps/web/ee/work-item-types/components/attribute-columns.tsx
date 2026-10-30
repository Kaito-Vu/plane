import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { useTranslation } from "@plane/i18n";
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
import { useMember } from "@/hooks/store/use-member";
import { formatAttributeValue } from "../attribute-display";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import type { TAttribute } from "../types";

/** Display-property key of an attribute column (saved with the other display properties). */
export const attributeColumnKey = (attributeId: string) => `attribute:${attributeId}`;

const isOn = (displayProperties: IIssueDisplayProperties | undefined, attributeId: string) =>
  !!(displayProperties as Record<string, unknown> | undefined)?.[attributeColumnKey(attributeId)];

/** Project attributes whose column is switched on. */
const useEnabledAttributes = (projectId: string | null | undefined, displayProperties?: IIssueDisplayProperties) => {
  const { workspaceSlug } = useParams();
  const { getProjectAttributes } = useAttributes();
  useEnsureProjectTypes(workspaceSlug?.toString(), projectId);
  return getProjectAttributes(projectId).filter((a) => isOn(displayProperties, a.id));
};

/** Display-properties dropdown: one toggle per attribute (fixed and custom) of the current project. */
export const AttributeDisplayPropertyToggles = observer(function AttributeDisplayPropertyToggles(props: {
  displayProperties: IIssueDisplayProperties;
  handleUpdate: (updated: Partial<IIssueDisplayProperties>) => void;
}) {
  const { displayProperties, handleUpdate } = props;
  const { workspaceSlug, projectId } = useParams();
  const { getProjectAttributes, getTypeKey } = useAttributes();
  const { t } = useTranslation();
  useEnsureProjectTypes(workspaceSlug?.toString(), projectId?.toString());
  const attributes = getProjectAttributes(projectId?.toString());
  if (attributes.length === 0) return null;
  return (
    <>
      {attributes.map((a) => {
        const typeKey = getTypeKey(projectId?.toString(), a.issue_type);
        const on = isOn(displayProperties, a.id);
        return (
          <button
            key={a.id}
            type="button"
            title={typeKey ? t(`agile_attributes.types.${typeKey}`) : undefined}
            className={`rounded-sm border px-2 py-0.5 text-11 transition-all ${
              on ? "border-accent-strong bg-accent-primary text-on-color" : "border-subtle hover:bg-layer-1"
            }`}
            onClick={() => handleUpdate({ [attributeColumnKey(a.id)]: !on } as Partial<IIssueDisplayProperties>)}
          >
            {a.name}
          </button>
        );
      })}
    </>
  );
});

/** Fetches only when `needed` (an enabled column belongs to the issue's type): no columns, no requests. */
const useIssueValues = (issue: TIssue, needed: boolean) => {
  const { workspaceSlug } = useParams();
  const { valuesByIssue, ensureIssueValues } = useAttributes();
  useEffect(() => {
    if (needed && workspaceSlug && issue.project_id && issue.id && !issue.tempId)
      ensureIssueValues(workspaceSlug.toString(), issue.project_id, issue.id);
  }, [needed, workspaceSlug, issue.project_id, issue.id, issue.tempId, ensureIssueValues]);
  return valuesByIssue[issue.id];
};

const useFormatter = () => {
  const { getUserDetails } = useMember();
  return (attribute: TAttribute, value: unknown) =>
    formatAttributeValue(attribute, value, (id) => getUserDetails(id)?.display_name);
};

/** Spreadsheet header cells for the enabled attribute columns. */
export const AttributeHeaderCells = observer(function AttributeHeaderCells(props: {
  displayProperties: IIssueDisplayProperties;
}) {
  const { projectId } = useParams();
  const attributes = useEnabledAttributes(projectId?.toString(), props.displayProperties);
  return (
    <>
      {attributes.map((a) => (
        <th
          key={a.id}
          className="h-11 min-w-36 items-center border border-t-0 border-b-0 border-subtle bg-layer-1 px-4 py-1 text-left text-13 font-medium"
        >
          {a.name}
        </th>
      ))}
    </>
  );
});

/** Spreadsheet row cells (read-only; edit in the detail panel). */
export const AttributeRowCells = observer(function AttributeRowCells(props: {
  displayProperties: IIssueDisplayProperties;
  issue: TIssue;
}) {
  const { displayProperties, issue } = props;
  const attributes = useEnabledAttributes(issue.project_id, displayProperties);
  const values = useIssueValues(
    issue,
    attributes.some((a) => a.issue_type === issue.type_id)
  );
  const format = useFormatter();
  return (
    <>
      {attributes.map((a) => (
        <td
          key={a.id}
          className="h-11 min-w-36 truncate border-r-[1px] border-subtle px-4 text-13 after:absolute after:bottom-[-1px] after:w-full after:border after:border-subtle"
        >
          {a.issue_type === issue.type_id ? format(a, values?.[a.id]) : ""}
        </td>
      ))}
    </>
  );
});

/** List/kanban: enabled attribute values as small chips. */
export const AttributeListProperties = observer(function AttributeListProperties(props: {
  displayProperties: IIssueDisplayProperties;
  issue: TIssue;
}) {
  const { displayProperties, issue } = props;
  const attributes = useEnabledAttributes(issue.project_id, displayProperties).filter(
    (a) => a.issue_type === issue.type_id
  );
  const values = useIssueValues(issue, attributes.length > 0);
  const format = useFormatter();
  return (
    <>
      {attributes.map((a) => {
        const text = format(a, values?.[a.id]);
        if (!text) return null;
        return (
          <span
            key={a.id}
            title={a.name}
            className="flex h-5 flex-shrink-0 items-center rounded-sm border-[0.5px] border-strong px-2 text-11"
          >
            <span className="text-tertiary">{a.name}:</span>&nbsp;{text}
          </span>
        );
      })}
    </>
  );
});
