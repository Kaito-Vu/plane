import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
import type { RootStore } from "@/store/root.store";
import { PARENT_RULES_UI } from "../constants";
import { AttributeService } from "../services/attribute.service";
import type { TAttribute, TWorkItemTypeKey } from "../types";

export interface IAttributeStore {
  attributesByProject: Record<string, TAttribute[]>;
  typeIdByKey: Partial<Record<TWorkItemTypeKey, string>>;
  setTypeIds: (map: Partial<Record<TWorkItemTypeKey, string>>) => void;
  getAttributesByType: (projectId: string, typeKey: TWorkItemTypeKey) => TAttribute[];
  allowedParentTypes: (typeKey: TWorkItemTypeKey) => TWorkItemTypeKey[];
  fetchProjectAttributes: (workspaceSlug: string, projectId: string) => Promise<TAttribute[]>;
}

export class AttributeStore implements IAttributeStore {
  attributesByProject: Record<string, TAttribute[]> = {};
  // IssueType id per agile key (backend attributes reference type ids); seeded by whoever loads workspace types.
  typeIdByKey: Partial<Record<TWorkItemTypeKey, string>> = {};
  private service = new AttributeService();

  // rootStore kept for the standard store constructor signature
  constructor(_rootStore: RootStore) {
    makeObservable(this, {
      attributesByProject: observable,
      typeIdByKey: observable,
      setTypeIds: action,
      fetchProjectAttributes: action,
    });
  }

  setTypeIds = (map: Partial<Record<TWorkItemTypeKey, string>>) => {
    this.typeIdByKey = map;
  };

  getAttributesByType = computedFn((projectId: string, typeKey: TWorkItemTypeKey): TAttribute[] => {
    const typeId = this.typeIdByKey[typeKey];
    if (!typeId) return [];
    return (this.attributesByProject[projectId] ?? [])
      .filter((a) => a.issue_type === typeId && a.is_active)
      .toSorted((a, b) => a.sort_order - b.sort_order);
  });

  allowedParentTypes = (typeKey: TWorkItemTypeKey): TWorkItemTypeKey[] => PARENT_RULES_UI[typeKey] ?? [];

  fetchProjectAttributes = async (workspaceSlug: string, projectId: string) => {
    const attrs = await this.service.getAttributes(workspaceSlug, projectId);
    runInAction(() => {
      this.attributesByProject[projectId] = attrs;
    });
    return attrs;
  };
}
