import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
import type { RootStore } from "@/store/root.store";
import { PARENT_RULES_UI } from "../constants";
import { AttributeService } from "../services/attribute.service";
import type { TAttribute, TProjectWorkItemType, TWorkItemTypeKey } from "../types";

type TTypeIds = Partial<Record<TWorkItemTypeKey, string>>;

export interface IAttributeStore {
  attributesByProject: Record<string, TAttribute[]>;
  typeIdsByProject: Record<string, TTypeIds>;
  setProjectTypes: (projectId: string, list: TProjectWorkItemType[]) => void;
  getAttributesByType: (projectId: string, typeKey: TWorkItemTypeKey) => TAttribute[];
  allowedParentTypes: (typeKey: TWorkItemTypeKey) => TWorkItemTypeKey[];
  fetchProjectAttributes: (workspaceSlug: string, projectId: string) => Promise<TAttribute[]>;
  fetchProjectTypes: (workspaceSlug: string, projectId: string) => Promise<TProjectWorkItemType[]>;
}

export class AttributeStore implements IAttributeStore {
  attributesByProject: Record<string, TAttribute[]> = {};
  // IssueType id per agile key, per project (attributes reference type ids)
  typeIdsByProject: Record<string, TTypeIds> = {};
  private service = new AttributeService();

  // rootStore kept for the standard store constructor signature
  constructor(_rootStore: RootStore) {
    makeObservable(this, {
      attributesByProject: observable,
      typeIdsByProject: observable,
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
    return [...(this.attributesByProject[projectId] ?? [])]
      .filter((a) => a.issue_type === typeId && a.is_active)
      .sort((a, b) => a.sort_order - b.sort_order);
  });

  // ponytail: parent rules are static per type key, so no project argument needed
  allowedParentTypes = (typeKey: TWorkItemTypeKey): TWorkItemTypeKey[] => PARENT_RULES_UI[typeKey] ?? [];

  fetchProjectAttributes = async (workspaceSlug: string, projectId: string) => {
    const attrs = await this.service.getAttributes(workspaceSlug, projectId);
    runInAction(() => {
      this.attributesByProject[projectId] = attrs;
    });
    return attrs;
  };

  fetchProjectTypes = async (workspaceSlug: string, projectId: string) => {
    const list = await this.service.fetchProjectTypes(workspaceSlug, projectId);
    this.setProjectTypes(projectId, list);
    return list;
  };
}
