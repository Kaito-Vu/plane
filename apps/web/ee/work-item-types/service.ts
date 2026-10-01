/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AxiosResponse } from "axios";
import { API_BASE_URL } from "@plane/constants";
import type { TIssueType, TIssueTypeUsage, TProjectWorkItemTypes, TWorkItemProcess } from "@plane/types";
import { APIService } from "@/services/api.service";

// Errors are rethrown as the DRF body so callers can show it (same convention as the other web services).
const unwrap = <T>(request: Promise<AxiosResponse<T>>): Promise<T> =>
  request
    .then((res) => res?.data)
    .catch((err) => {
      throw err?.response?.data;
    });

export class WorkItemTypeService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private base = (slug: string) => `/api/workspaces/${slug}/work-item-types/`;
  private projectBase = (slug: string, projectId: string) =>
    `/api/workspaces/${slug}/projects/${projectId}/work-item-types/`;

  list = (slug: string): Promise<TIssueType[]> => unwrap(this.get(this.base(slug)));
  create = (slug: string, data: Partial<TIssueType>): Promise<TIssueType> => unwrap(this.post(this.base(slug), data));
  update = (slug: string, id: string, data: Partial<TIssueType>): Promise<TIssueType> =>
    unwrap(this.patch(`${this.base(slug)}${id}/`, data));
  remove = (slug: string, id: string, migrateTo?: string): Promise<void> =>
    unwrap(this.delete(`${this.base(slug)}${id}/`, undefined, { params: migrateTo ? { migrate_to: migrateTo } : {} }));

  /** Workspace admin: seed the Scrum + Agile presets (idempotent), returns the full list. */
  seed = (slug: string): Promise<TIssueType[]> => unwrap(this.post(`${this.base(slug)}seed/`, {}));
  usage = (slug: string, id: string): Promise<TIssueTypeUsage> => unwrap(this.get(`${this.base(slug)}${id}/usage/`));

  getProject = (slug: string, projectId: string): Promise<TProjectWorkItemTypes> =>
    unwrap(this.get(this.projectBase(slug, projectId)));
  setProcess = (
    slug: string,
    projectId: string,
    process: TWorkItemProcess,
    migrate?: boolean
  ): Promise<{ process: TWorkItemProcess }> =>
    unwrap(this.post(this.projectBase(slug, projectId), migrate ? { process, migrate } : { process }));
  assign = (slug: string, projectId: string, typeId: string): Promise<{ type_id: string }> =>
    unwrap(this.post(`${this.projectBase(slug, projectId)}assign/`, { type_id: typeId }));
  unassign = (slug: string, projectId: string, typeId: string): Promise<void> =>
    unwrap(this.delete(`${this.projectBase(slug, projectId)}assign/${typeId}/`));
  setDefault = (slug: string, projectId: string, typeId: string): Promise<void> =>
    unwrap(this.post(`${this.projectBase(slug, projectId)}default/`, { type_id: typeId }));
  /** Uses the existing project PATCH (spec: enable/disable has no dedicated endpoint). */
  setEnabled = (slug: string, projectId: string, enabled: boolean): Promise<unknown> =>
    unwrap(this.patch(`/api/workspaces/${slug}/projects/${projectId}/`, { is_issue_type_enabled: enabled }));
}
