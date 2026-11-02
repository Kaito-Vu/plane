import { store } from "@/lib/store-context";

/** Per-group "load more" for EE group keys (`type`, `attribute:<id>`): the core maps a group key to a legacy
 * query param, which has no equivalent here, so AND the group condition into the rich `filters` JSON. */
export const isEeGroupKey = (key: string) => key === "type" || key.startsWith("attribute:");

export const withEeGroupFilter = (params: Record<string, unknown>, groupKey: string, groupId: string) => {
  // "None" = no type / no value for the attribute (backend `__isnull`)
  const condition = groupId === "None" ? { [`${groupKey}__isnull`]: "true" } : { [`${groupKey}__in`]: groupId };
  let current: unknown;
  try {
    current = typeof params.filters === "string" ? JSON.parse(params.filters) : undefined;
  } catch {
    current = undefined;
  }
  const hasCurrent = current && typeof current === "object" && Object.keys(current).length > 0;
  params.filters = JSON.stringify(hasCurrent ? { and: [current, condition] } : condition);
};

/** A saved `attribute:<id>` group key whose attribute was deleted/deactivated (only once attributes are
 * loaded). Such keys are dropped from the request and the layout falls back to one ungrouped column. */
export const isStaleEeGroupKey = (key: string | null | undefined): boolean => {
  if (!key?.startsWith("attribute:")) return false;
  const loaded = Object.values(store.attribute.attributesByProject);
  if (loaded.length === 0) return false;
  const id = key.slice("attribute:".length);
  return !loaded.some((list) => list.some((a) => a.id === id && a.is_active));
};
