import type { IInstanceAdmin } from "@plane/types";
import { InstanceService } from "@plane/services";

/**
 * God-mode API calls. Reuses the authenticated HTTP client of InstanceService (get/post/delete are public),
 * so no core service file needs to change.
 */
class GodModeService extends InstanceService {
  async addAdmin(email: string): Promise<IInstanceAdmin> {
    return this.post("/api/instances/admins/", { email })
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async removeAdmin(id: string): Promise<void> {
    return this.delete(`/api/instances/admins/${id}/`)
      .then(() => undefined)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async deleteWorkspace(slug: string): Promise<void> {
    return this.delete(`/api/instances/workspaces/${encodeURIComponent(slug)}/`)
      .then(() => undefined)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async archiveWorkspaceProjects(slug: string): Promise<{ archived_projects: number }> {
    return this.post(`/api/instances/workspaces/${encodeURIComponent(slug)}/archive/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async searchWorkspaceUsers(
    slug: string,
    search: string
  ): Promise<{ id: string; email: string; display_name: string; current_role: number | null }[]> {
    return this.get(`/api/instances/workspaces/${encodeURIComponent(slug)}/members/`, { params: { search } })
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async assignWorkspaceMember(slug: string, email: string, role: number): Promise<{ created: boolean }> {
    return this.post(`/api/instances/workspaces/${encodeURIComponent(slug)}/members/`, { email, role })
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async getExternalInvites(): Promise<{ enabled: boolean }> {
    return this.get("/api/instances/external-invites/")
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async setExternalInvites(enabled: boolean): Promise<{ enabled: boolean }> {
    return this.patch("/api/instances/external-invites/", { enabled })
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }
}

export const godModeService = new GodModeService();
