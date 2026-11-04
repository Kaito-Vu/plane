import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TProjectMemberSearchResult = { id: string; display_name: string; avatar_url: string; email: string };

export class ProjectMemberSearchService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async search(workspaceSlug: string, projectId: string, q: string): Promise<TProjectMemberSearchResult[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/members/search/`, { params: { q } })
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async externalInvitesEnabled(): Promise<boolean> {
    return this.get(`/api/external-invites/`)
      .then((r) => Boolean(r?.data?.enabled))
      .catch(() => false);
  }
}

export const projectMemberSearchService = new ProjectMemberSearchService();
