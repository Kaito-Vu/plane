import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TAllocation = { start_date: string | null; end_date: string | null };
// keyed by project-member id; members without an allocation are absent
export type TAllocationMap = Record<string, TAllocation>;

export class ProjectMemberAllocationService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async list(workspaceSlug: string, projectId: string): Promise<TAllocationMap> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/members/allocations/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async update(workspaceSlug: string, projectId: string, projectMemberId: string, data: Partial<TAllocation>) {
    return this.patch(`/api/workspaces/${workspaceSlug}/projects/${projectId}/members/${projectMemberId}/`, data)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }
}

export const projectMemberAllocationService = new ProjectMemberAllocationService();
