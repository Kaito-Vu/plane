import { useMemo } from "react";
import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
import { useTranslation } from "@plane/i18n";
import type {
  IGroupByColumn,
  IUserLite,
  TFilterConfig,
  TIssueGroupByOptions,
  TOperatorSpecificConfigs,
  TSupportedOperators,
  TWorkItemFilterProperty,
} from "@plane/types";
import {
  COLLECTION_OPERATOR,
  COMPARISON_OPERATOR,
  EQUALITY_OPERATOR,
  EXTENDED_OPERATORS,
  FILTER_FIELD_TYPE,
} from "@plane/types";
import {
  createFilterConfig,
  createOperatorConfigEntry,
  getDatePickerConfig,
  getDateRangePickerConfig,
  getMultiSelectConfig,
  getSingleSelectConfig,
} from "@plane/utils";
import { MenuRadioItem } from "@makeplane/propel/components/menu";
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

const TEXT_TYPES = new Set(["text", "textarea", "url"]);
const DATE_TYPES = new Set(["date", "datetime"]);

/** Operators the core allows plus the EE ones (icontains, gte, lte, isnull). */
const withEeOperators = (params: TFiltersOperatorConfigs): TFiltersOperatorConfigs => ({
  ...params,
  allowedOperators: new Set([...params.allowedOperators, ...Object.values(EXTENDED_OPERATORS)]),
});

/** isnull as a two-option select: "true" = no value, "false" = has a value. */
const emptyEntry = (params: TFiltersOperatorConfigs) =>
  createOperatorConfigEntry(EQUALITY_OPERATOR.ISNULL, { isEnabled: true, ...params }, (updated) =>
    getSingleSelectConfig<TOption, string>(
      {
        items: [
          { id: "true", label: "yes" },
          { id: "false", label: "no" },
        ],
        getId: (o) => o.id,
        getLabel: (o) => o.label,
        getValue: (o) => o.id,
      },
      updated
    )
  );

/** Text (contains), number (=, >=, <=, between) and date (on, on/after, on/before, between) filters,
 * all with "is empty". Keys follow plane.ee.work_item_types.filters: `attribute:<id>__<op>`. */
const valueFilter = (a: TAttribute, label: string, base: TFiltersOperatorConfigs) => {
  const params = withEeOperators(base);
  const p = { isEnabled: true, ...params };
  // text/number field configs are plain objects (no factory in @plane/utils for the EE field types)
  const field = (type: string) => (updated: typeof p) => ({ type, ...updated }) as never;
  let entries: [TSupportedOperators, TOperatorSpecificConfigs[keyof TOperatorSpecificConfigs]][];
  if (TEXT_TYPES.has(a.field_type))
    entries = [createOperatorConfigEntry(EQUALITY_OPERATOR.ICONTAINS, p, field(FILTER_FIELD_TYPE.TEXT))];
  else if (a.field_type === "number")
    entries = [
      createOperatorConfigEntry(EQUALITY_OPERATOR.EXACT, p, field(FILTER_FIELD_TYPE.NUMBER)),
      createOperatorConfigEntry(COMPARISON_OPERATOR.GTE, p, field(FILTER_FIELD_TYPE.NUMBER)),
      createOperatorConfigEntry(COMPARISON_OPERATOR.LTE, p, field(FILTER_FIELD_TYPE.NUMBER)),
      createOperatorConfigEntry(COMPARISON_OPERATOR.RANGE, p, field(FILTER_FIELD_TYPE.NUMBER_RANGE)),
    ];
  else
    entries = [
      createOperatorConfigEntry(EQUALITY_OPERATOR.EXACT, p, (u) => getDatePickerConfig(u)),
      createOperatorConfigEntry(COMPARISON_OPERATOR.GTE, p, (u) => getDatePickerConfig(u)),
      createOperatorConfigEntry(COMPARISON_OPERATOR.LTE, p, (u) => getDatePickerConfig(u)),
      createOperatorConfigEntry(COMPARISON_OPERATOR.RANGE, p, (u) => getDateRangePickerConfig(u)),
    ];
  return createFilterConfig<TWorkItemFilterProperty>({
    id: `${ATTR}${a.id}` as TWorkItemFilterProperty,
    label,
    isEnabled: true,
    ...params,
    supportedOperatorConfigsMap: new Map([...entries, emptyEntry(params)]),
  });
};

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
    const typeKeyOf = Object.fromEntries(Object.entries(typeIds).map(([k, id]) => [id, k]));
    // names repeat across types (Story Points on Epic/Feature/Story/Bug): label with the type
    const label = (a: TAttribute) =>
      typeKeyOf[a.issue_type] ? `${a.name} (${t(`agile_attributes.types.${typeKeyOf[a.issue_type]}`)})` : a.name;
    return [
      multiSelect("type", t("agile_work_item.type"), typeOptions, operatorConfigs),
      ...attributes.flatMap((a) => {
        if (FILTERABLE.has(a.field_type))
          return [multiSelect(`${ATTR}${a.id}`, label(a), attributeOptions(a, members, t), operatorConfigs)];
        if (TEXT_TYPES.has(a.field_type) || a.field_type === "number" || DATE_TYPES.has(a.field_type))
          return [valueFilter(a, label(a), operatorConfigs)];
        return [];
      }),
    ];
  }, [projectId, typeIds, attributes, members, operatorConfigs, t]);
};

/** Group-by is resolved only by the project IssueViewSet list (not cycles/modules/views). */
const useEeGroupByAvailable = () => {
  const pathname = usePathname();
  return /\/projects\/[^/]+\/issues\/?$/.test(pathname ?? "");
};

/** Extra group-by options (type, select/member/boolean attributes); render inside the core `MenuRadioGroup`. */
export const AttributeGroupByOptions = observer(function AttributeGroupByOptions(props: {
  exclude?: TIssueGroupByOptions | null | undefined;
}) {
  const { exclude } = props;
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
          <MenuRadioItem key={o.key} value={o.key} label={o.title} />
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
export const getEeGroupByColumns = (
  groupBy: string,
  projectIdArg: string | undefined
): IGroupByColumn[] | undefined => {
  // list/kanban layouts call getGroupByColumns without projectId (core getters read the router store too)
  const projectId = projectIdArg ?? store.router.projectId;
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
