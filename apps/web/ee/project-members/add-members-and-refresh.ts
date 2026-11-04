type TPayload = { members: { member_id: string; role: number }[] };

// The core store's bulk add only writes projectMemberMap; a user new to the workspace stays invisible until the
// workspace member map is refetched, so refresh it (then the project members) after a successful add.
// An add failure propagates; refresh failures are tolerated and reported so the caller can warn the admin.
export const addMembersAndRefresh = async (
  deps: {
    add: (workspaceSlug: string, projectId: string, payload: TPayload) => Promise<unknown>;
    refreshWorkspace: (workspaceSlug: string) => Promise<unknown>;
    refreshProject: (workspaceSlug: string, projectId: string) => Promise<unknown>;
  },
  args: { workspaceSlug: string; projectId: string; payload: TPayload }
): Promise<{ failedRefreshes: ("workspace" | "project")[] }> => {
  const { workspaceSlug, projectId, payload } = args;
  await deps.add(workspaceSlug, projectId, payload);
  const failedRefreshes: ("workspace" | "project")[] = [];
  const steps = [
    ["workspace", () => deps.refreshWorkspace(workspaceSlug)],
    ["project", () => deps.refreshProject(workspaceSlug, projectId)],
  ] as const;
  for (const [name, refresh] of steps) {
    try {
      await refresh();
    } catch (error) {
      console.error(error);
      failedRefreshes.push(name);
    }
  }
  return { failedRefreshes };
};
