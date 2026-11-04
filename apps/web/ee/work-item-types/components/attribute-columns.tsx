import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Menu as BaseMenu } from "@base-ui/react/menu";
import { Toggle, ToggleLabel } from "@makeplane/propel/elements/toggle";
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

/** Attributes grouped by name: types often share a name (Story Points on Story/Task/...), shown as one toggle
 * and one column. Keys stay per attribute id; a toggle flips every id of its name. */
const byName = (attributes: TAttribute[]) => {
  const groups = new Map<string, TAttribute[]>();
  for (const a of attributes) groups.set(a.name, [...(groups.get(a.name) ?? []), a]);
  return [...groups.entries()].map(([name, attrs]) => ({ name, attrs }));
};

/** Enabled attribute columns (one per name). */
const useEnabledColumns = (projectId: string | null | undefined, displayProperties?: IIssueDisplayProperties) => {
  const { workspaceSlug } = useParams();
  const { getProjectAttributes } = useAttributes();
  useEnsureProjectTypes(workspaceSlug?.toString(), projectId);
  return byName(getProjectAttributes(projectId).filter((a) => isOn(displayProperties, a.id)));
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
  const groups = byName(getProjectAttributes(projectId?.toString()));
  if (groups.length === 0) return null;
  return (
    <>
      {groups.map(({ name, attrs }) => {
        const types = attrs
          .map((a) => getTypeKey(projectId?.toString(), a.issue_type))
          .filter(Boolean)
          .map((k) => t(`agile_attributes.types.${k}`));
        const on = attrs.some((a) => isOn(displayProperties, a.id));
        return (
          <BaseMenu.CheckboxItem
            key={name}
            title={types.join(", ")}
            checked={on}
            closeOnClick={false}
            onCheckedChange={(checked) =>
              handleUpdate(
                Object.fromEntries(
                  attrs.map((a) => [attributeColumnKey(a.id), checked])
                ) as Partial<IIssueDisplayProperties>
              )
            }
            render={<Toggle size="sm" render={<div />} data-pressed={on ? "" : undefined} />}
          >
            <ToggleLabel>{name}</ToggleLabel>
          </BaseMenu.CheckboxItem>
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
  const columns = useEnabledColumns(projectId?.toString(), props.displayProperties);
  return (
    <>
      {columns.map(({ name }) => (
        <th
          key={name}
          className="h-11 min-w-36 items-center border border-t-0 border-b-0 border-subtle bg-layer-1 px-4 py-1 text-left text-13 font-medium"
        >
          {name}
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
  const columns = useEnabledColumns(issue.project_id, displayProperties).map(({ name, attrs }) => ({
    name,
    attr: attrs.find((a) => a.issue_type === issue.type_id),
  }));
  const values = useIssueValues(
    issue,
    columns.some((c) => c.attr)
  );
  const format = useFormatter();
  return (
    <>
      {columns.map(({ name, attr }) => (
        <td
          key={name}
          className="h-11 min-w-36 truncate border-r-[1px] border-subtle px-4 text-13 after:absolute after:bottom-[-1px] after:w-full after:border after:border-subtle"
        >
          {attr ? format(attr, values?.[attr.id]) : ""}
        </td>
      ))}
    </>
  );
});

/** List/kanban: enabled attribute values with a value, as {id, name, text} chips for the issue's type. */
export const useAttributeChips = (displayProperties: IIssueDisplayProperties | undefined, issue: TIssue) => {
  const attributes = useEnabledColumns(issue.project_id, displayProperties)
    .flatMap(({ attrs }) => attrs)
    .filter((a) => a.issue_type === issue.type_id);
  const values = useIssueValues(issue, attributes.length > 0);
  const format = useFormatter();
  return attributes.flatMap((a) => {
    const text = format(a, values?.[a.id]);
    return text ? [{ id: a.id, name: a.name, text }] : [];
  });
};
