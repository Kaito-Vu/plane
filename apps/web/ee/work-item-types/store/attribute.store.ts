import { action, makeObservable, observable, runInAction } from "mobx";
import { sortBy } from "lodash-es";
import { computedFn } from "mobx-utils";
import type { RootStore } from "@/store/root.store";
import { PARENT_RULES_UI } from "../constants";
import { AttributeService } from "../services/attribute.service";
import type { TAttribute, TAttributeValues, TProjectWorkItemType, TWorkItemTypeKey } from "../types";

type TTypeIds = Partial<Record<TWorkItemTypeKey, string>>;

export interface IAttributeStore {
  attributesByProject: Record<string, TAttribute[]>;
  typeIdsByProject: Record<string, TTypeIds>;
  setProjectTypes: (projectId: string, list: TProjectWorkItemType[]) => void;
  getAttributesByType: (projectId: string, typeKey: TWorkItemTypeKey) => TAttribute[];
  allowedParentTypes: (typeKey: TWorkItemTypeKey) => TWorkItemTypeKey[];
  getTypeKey: (projectId: string | null | undefined, typeId: string | null | undefined) => TWorkItemTypeKey | undefined;
  getTypeId: (projectId: string | null | undefined, typeKey: TWorkItemTypeKey) => string | undefined;
  fetchProjectAttributes: (workspaceSlug: string, projectId: string) => Promise<TAttribute[]>;
  fetchProjectTypes: (workspaceSlug: string, projectId: string) => Promise<TProjectWorkItemType[]>;
  /** Fetch a project's types and attributes once per session (concurrent callers share the request). */
  ensureProject: (workspaceSlug: string, projectId: string) => Promise<void>;
  /** Active attributes of every type in the project (columns, filters, group by). */
  getProjectAttributes: (projectId: string | null | undefined) => TAttribute[];
  valuesByIssue: Record<string, TAttributeValues>;
  /** Attribute values of one issue, fetched once per session (columns). */
  ensureIssueValues: (workspaceSlug: string, projectId: string, issueId: string) => void;
  setIssueValues: (issueId: string, values: TAttributeValues) => void;
}

export class AttributeStore implements IAttributeStore {
  attributesByProject: Record<string, TAttribute[]> = {};
  // IssueType id per agile key, per project (attributes reference type ids)
  typeIdsByProject: Record<string, TTypeIds> = {};
  private service = new AttributeService();
  private ensured: Record<string, Promise<void>> = {};
  valuesByIssue: Record<string, TAttributeValues> = {};
  private valuesRequested = new Set<string>();

  // rootStore kept for the standard store constructor signature
  constructor(_rootStore: RootStore) {
    makeObservable(this, {
      attributesByProject: observable,
      typeIdsByProject: observable,
      valuesByIssue: observable,
      setIssueValues: action,
      setProjectTypes: action,
      fetchProjectAttributes: action,
      fetchProjectTypes: action,
    });
  }

  setProjectTypes = (projectId: string, list: TProjectWorkItemType[]) => {
    this.typeIdsByProject[projectId] = Object.fromEntries(list.map((t) => [t.key, t.id]));
  };

  getAttributesByType = computedFn((projectId: string, typeKey: TWorkItemTypeKey): TAttribute[] => {
    const typeId = this.typeIdsByProject[projectId]?.[typeKey];
    if (!typeId) return [];
    return sortBy(
      [...(this.attributesByProject[projectId] ?? [])].filter((a) => a.issue_type === typeId && a.is_active),
      "sort_order"
    );
  });

  // ponytail: parent rules are static per type key, so no project argument needed
  allowedParentTypes = (typeKey: TWorkItemTypeKey): TWorkItemTypeKey[] => PARENT_RULES_UI[typeKey] ?? [];

  getTypeKey = computedFn(
    (projectId: string | null | undefined, typeId: string | null | undefined): TWorkItemTypeKey | undefined => {
      if (!projectId || !typeId) return undefined;
      const ids = this.typeIdsByProject[projectId] ?? {};
      return (Object.keys(ids) as TWorkItemTypeKey[]).find((k) => ids[k] === typeId);
    }
  );

  getTypeId = (projectId: string | null | undefined, typeKey: TWorkItemTypeKey) =>
    projectId ? this.typeIdsByProject[projectId]?.[typeKey] : undefined;

  fetchProjectAttributes = async (workspaceSlug: string, projectId: string) => {
    const attrs = await this.service.getAttributes(workspaceSlug, projectId);
    runInAction(() => {
      this.attributesByProject[projectId] = attrs;
    });
    return attrs;
  };

  ensureProject = (workspaceSlug: string, projectId: string) => {
    this.ensured[projectId] ??= Promise.all([
      this.fetchProjectTypes(workspaceSlug, projectId),
      this.fetchProjectAttributes(workspaceSlug, projectId),
    ])
      .then(() => undefined)
      .catch((err) => {
        delete this.ensured[projectId]; // allow a retry
        console.error(err);
      });
    return this.ensured[projectId];
  };

  getProjectAttributes = computedFn((projectId: string | null | undefined): TAttribute[] =>
    projectId
      ? sortBy(
          (this.attributesByProject[projectId] ?? []).filter((a) => a.is_active),
          "sort_order"
        )
      : []
  );

  // ponytail: one request per visible issue (list API has no values); embed values in the list API if this hurts
  ensureIssueValues = (workspaceSlug: string, projectId: string, issueId: string) => {
    if (this.valuesRequested.has(issueId)) return;
    this.valuesRequested.add(issueId);
    this.service
      .getAttributeValues(workspaceSlug, projectId, issueId)
      .then((values) => runInAction(() => (this.valuesByIssue[issueId] = values)))
      .catch((err) => {
        this.valuesRequested.delete(issueId);
        console.error(err);
      });
  };

  setIssueValues = (issueId: string, values: TAttributeValues) => {
    this.valuesRequested.add(issueId);
    this.valuesByIssue[issueId] = values;
  };

  fetchProjectTypes = async (workspaceSlug: string, projectId: string) => {
    const list = await this.service.fetchProjectTypes(workspaceSlug, projectId);
    this.setProjectTypes(projectId, list);
    return list;
  };
}
