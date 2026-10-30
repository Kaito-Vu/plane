import { useMemo } from "react";
import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
import { useTranslation } from "@plane/i18n";
import type {
  IGroupByColumn,
  IUserLite,
  TFilterConfig,
  TIssueGroupByOptions,
  TWorkItemFilterProperty,
} from "@plane/types";
import { COLLECTION_OPERATOR, EQUALITY_OPERATOR } from "@plane/types";
import { createFilterConfig, createOperatorConfigEntry, getMultiSelectConfig } from "@plane/utils";
import { FilterOption } from "@/components/issues/issue-layouts/filters";
import type { TFiltersOperatorConfigs } from "@/hooks/rich-filters/use-filters-operator-configs";
import { store } from "@/lib/store-context";
import { ALL_ISSUES } from "@plane/constants";
import { TYPE_KEYS } from "../constants";
import { isStaleEeGroupKey } from "../group-filter";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import type { TAttribute, TWorkItemTypeKey } from "../types";
import { TypeKeyBadge } from "./type-badge";

const GROUPABLE = new Set(["select", "member", "boolean"]);
const FILTERABLE = new Set(["select", "multi_select", "member", "multi_member", "boolean"]);
const ATTR = "attribute:";

type TOption = { id: string; label: string };

const multiSelect = (key: string, label: string, options: TOption[], params: TFiltersOperatorConfigs) =>
  createFilterConfig<TWorkItemFilterProperty>({
    // backend keys `type` / `attribute:<id>` (plane.ee.work_item_types.filters); the adapter seam lets them through
    id: key as TWorkItemFilterProperty,
    label,
    isEnabled: true,
    ...params,
    supportedOperatorConfigsMap: new Map([
      createOperatorConfigEntry(COLLECTION_OPERATOR.IN, { isEnabled: true, ...params }, (updated) =>
        getMultiSelectConfig<TOption, string>(
          { items: options, getId: (o) => o.id, getLabel: (o) => o.label, getValue: (o) => o.id },
          { singleValueOperator: EQUALITY_OPERATOR.EXACT, ...updated }
        )
      ),
    ]),
  });

const attributeOptions = (a: TAttribute, members: IUserLite[], t: (key: string) => string): TOption[] => {
  if (a.field_type === "boolean")
    return [
      { id: "true", label: t("agile_attributes.boolean.yes") },
      { id: "false", label: t("agile_attributes.boolean.no") },
    ];
  if (a.field_type === "member" || a.field_type === "multi_member")
    return members.map((m) => ({ id: m.id, label: m.display_name }));
  return a.options.filter((o) => o.is_active).map((o) => ({ id: o.id, label: o.name }));
};

/** Rich-filter configs: work item type + each select/member/boolean attribute of the project. */
export const useAttributeFilterConfigs = (
  workspaceSlug: string,
  projectId: string | undefined,
  members: IUserLite[],
  operatorConfigs: TFiltersOperatorConfigs
): TFilterConfig<TWorkItemFilterProperty>[] => {
  const { t } = useTranslation();
  const { getProjectAttributes, typeIdsByProject } = useAttributes();
  useEnsureProjectTypes(workspaceSlug, projectId);
  const attributes = getProjectAttributes(projectId);
  const typeIds = projectId ? typeIdsByProject[projectId] : undefined;
  return useMemo(() => {
    if (!projectId || !typeIds) return [];
    const typeOptions = TYPE_KEYS.filter((k) => typeIds[k]).map((k) => ({
      id: typeIds[k] as string,
      label: t(`agile_attributes.types.${k}`),
    }));
    return [
      multiSelect("type", t("agile_work_item.type"), typeOptions, operatorConfigs),
      ...attributes
        .filter((a) => FILTERABLE.has(a.field_type))
        .map((a) => multiSelect(`${ATTR}${a.id}`, a.name, attributeOptions(a, members, t), operatorConfigs)),
    ];
  }, [projectId, typeIds, attributes, members, operatorConfigs, t]);
};

/** Group-by is resolved only by the project IssueViewSet list (not cycles/modules/views). */
const useEeGroupByAvailable = () => {
  const pathname = usePathname();
  return /\/projects\/[^/]+\/issues\/?$/.test(pathname ?? "");
};

/** Extra group-by options (type, select/member/boolean attributes) under the core ones. */
export const AttributeGroupByOptions = observer(function AttributeGroupByOptions(props: {
  selected: TIssueGroupByOptions | undefined;
  exclude?: TIssueGroupByOptions | undefined;
  onSelect: (key: TIssueGroupByOptions) => void;
}) {
  const { selected, exclude, onSelect } = props;
  const { workspaceSlug, projectId } = useParams();
  const { t } = useTranslation();
  const { getProjectAttributes, typeIdsByProject } = useAttributes();
  useEnsureProjectTypes(workspaceSlug?.toString(), projectId?.toString());
  const available = useEeGroupByAvailable();
  if (!available || !projectId) return null;
  const hasTypes = Object.keys(typeIdsByProject[projectId.toString()] ?? {}).length > 0;
  const options: { key: TIssueGroupByOptions; title: string }[] = [
    ...(hasTypes ? [{ key: "type" as TIssueGroupByOptions, title: t("agile_work_item.type") }] : []),
    ...getProjectAttributes(projectId.toString())
      .filter((a) => GROUPABLE.has(a.field_type))
      .map((a) => ({ key: `${ATTR}${a.id}` as TIssueGroupByOptions, title: a.name })),
  ];
  return (
    <>
      {options
        .filter((o) => o.key !== exclude)
        .map((o) => (
          <FilterOption
            key={o.key}
            isChecked={selected === o.key}
            onClick={() => onSelect(o.key)}
            title={o.title}
            multiple={false}
          />
        ))}
    </>
  );
});

const column = (id: string, name: string): IGroupByColumn => ({
  id,
  name,
  payload: {},
  isDropDisabled: true,
  dropErrorMessage: "Edit the attribute in the work item",
});

const humanize = (key: string) => key.charAt(0).toUpperCase() + key.slice(1).replace("_", " ");

/** Columns for EE group keys; group ids match the backend (uuid strings, "True"/"False", "None"). */
export const getEeGroupByColumns = (groupBy: string, projectId: string | undefined): IGroupByColumn[] | undefined => {
  if (!projectId) return undefined;
  const attributeStore = store.attribute;
  if (groupBy === "type") {
    const ids = attributeStore.typeIdsByProject[projectId] ?? {};
    return [
      ...TYPE_KEYS.filter((k) => ids[k]).map(
        (k: TWorkItemTypeKey): IGroupByColumn => ({
          id: ids[k] as string,
          name: humanize(k),
          icon: <TypeKeyBadge typeKey={k} compact />,
          payload: {},
          isDropDisabled: true,
          dropErrorMessage: "Type cannot be changed",
        })
      ),
      column("None", "None"), // untyped (pre-migration) issues
    ];
  }
  // saved group-by on a deleted attribute: the request is sent ungrouped (isStaleEeGroupKey)
  if (isStaleEeGroupKey(groupBy)) return [column(ALL_ISSUES, "All work items")];
  if (!groupBy.startsWith(ATTR)) return undefined;
  const attribute = attributeStore.getProjectAttributes(projectId).find((a) => a.id === groupBy.slice(ATTR.length));
  if (!attribute) return undefined;
  // ponytail: attribute groups are read-only (drag would need an attribute-value write); edit in the detail panel
  const none = column("None", "None");
  if (attribute.field_type === "boolean") return [column("True", "Yes"), column("False", "No"), none];
  if (attribute.field_type === "select")
    return [...attribute.options.filter((o) => o.is_active).map((o) => column(o.id, o.name)), none];
  const memberIds = store.memberRoot.project.getProjectMemberIds(projectId, false) ?? [];
  return [...memberIds.map((id) => column(id, store.memberRoot.getUserDetails(id)?.display_name ?? id)), none];
};
