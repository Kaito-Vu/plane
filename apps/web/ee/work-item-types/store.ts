/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import type { TIssueType, TProjectIssueType, TProjectWorkItemTypes, TWorkItemProcess } from "@plane/types";
import { defaultTypeId } from "./rules";
import type { WorkItemTypeService } from "./service";

const EMPTY: TProjectIssueType[] = [];

export class WorkItemTypeStore {
  projectMap: Record<string, TProjectWorkItemTypes> = {};
  workspaceMap: Record<string, TIssueType[]> = {};

  constructor(private service: WorkItemTypeService) {
    makeObservable(this, {
      projectMap: observable,
      workspaceMap: observable,
      setProject: action,
      setWorkspace: action,
    });
  }

  setProject = (projectId: string, data: TProjectWorkItemTypes) => {
    this.projectMap[projectId] = data;
  };
  setWorkspace = (slug: string, types: TIssueType[]) => {
    this.workspaceMap[slug] = types;
  };

  // getters
  getProject = (projectId: string | null | undefined) => (projectId ? this.projectMap[projectId] : undefined);
  /** Types usable in this project; empty when the feature is off or not loaded (callers then hide their UI). */
  getProjectTypes = (projectId: string | null | undefined): TProjectIssueType[] => {
    const config = this.getProject(projectId);
    return config?.enabled ? config.types : EMPTY;
  };
  /** `type_id = null` on legacy issues means the project default. */
  resolveType = (projectId: string | null | undefined, typeId: string | null | undefined) => {
    const types = this.getProjectTypes(projectId);
    const id = typeId ?? defaultTypeId(types);
    return types.find((type) => type.id === id);
  };
  isEpic = (projectId: string | null | undefined, typeId: string | null | undefined) =>
    !!this.resolveType(projectId, typeId)?.is_epic;
  getWorkspaceTypes = (slug: string | null | undefined) => (slug ? this.workspaceMap[slug] : undefined);

  // fetch
  fetchProject = async (slug: string, projectId: string) => {
    const data = await this.service.getProject(slug, projectId);
    this.setProject(projectId, data);
    return data;
  };
  fetchWorkspace = async (slug: string) => {
    const types = await this.service.list(slug);
    this.setWorkspace(slug, types);
    return types;
  };

  // workspace CRUD (workspace admin)
  createType = async (slug: string, data: Partial<TIssueType>) => {
    const created = await this.service.create(slug, data);
    runInAction(() => {
      this.workspaceMap[slug] = [...(this.workspaceMap[slug] ?? []), created];
    });
    return created;
  };
  updateType = async (slug: string, id: string, data: Partial<TIssueType>) => {
    const updated = await this.service.update(slug, id, data);
    runInAction(() => {
      this.workspaceMap[slug] = (this.workspaceMap[slug] ?? []).map((type) => (type.id === id ? updated : type));
    });
    return updated;
  };
  seedPresets = async (slug: string) => {
    const types = await this.service.seed(slug);
    this.setWorkspace(slug, types);
    return types;
  };
  getUsage = (slug: string, id: string) => this.service.usage(slug, id);
  deleteType = async (slug: string, id: string, migrateTo?: string) => {
    await this.service.remove(slug, id, migrateTo);
    await this.fetchWorkspace(slug);
  };

  // project (project admin) — always refetch: the server owns process/default/enabled derivation
  setProcess = async (slug: string, projectId: string, process: TWorkItemProcess, migrate?: boolean) => {
    await this.service.setProcess(slug, projectId, process, migrate);
    return this.fetchProject(slug, projectId);
  };
  assign = async (slug: string, projectId: string, typeId: string) => {
    await this.service.assign(slug, projectId, typeId);
    return this.fetchProject(slug, projectId);
  };
  unassign = async (slug: string, projectId: string, typeId: string) => {
    await this.service.unassign(slug, projectId, typeId);
    return this.fetchProject(slug, projectId);
  };
  setDefault = async (slug: string, projectId: string, typeId: string) => {
    await this.service.setDefault(slug, projectId, typeId);
    return this.fetchProject(slug, projectId);
  };
  setEnabled = async (slug: string, projectId: string, enabled: boolean) => {
    await this.service.setEnabled(slug, projectId, enabled);
    return this.fetchProject(slug, projectId);
  };
}
