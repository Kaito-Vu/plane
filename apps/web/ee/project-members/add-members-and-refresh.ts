type TPayload = { members: { member_id: string; role: number }[] };

// The core store's bulk add only writes projectMemberMap; a user new to the workspace stays invisible until the
// workspace member map is refetched, so refresh it (then the project members) after a successful add.
export const addMembersAndRefresh = async (
  deps: {
    add: (workspaceSlug: string, projectId: string, payload: TPayload) => Promise<unknown>;
    refreshWorkspace: (workspaceSlug: string) => Promise<unknown>;
    refreshProject: (workspaceSlug: string, projectId: string) => Promise<unknown>;
  },
  args: { workspaceSlug: string; projectId: string; payload: TPayload }
): Promise<void> => {
  const { workspaceSlug, projectId, payload } = args;
  await deps.add(workspaceSlug, projectId, payload);
  for (const refresh of [
    () => deps.refreshWorkspace(workspaceSlug),
    () => deps.refreshProject(workspaceSlug, projectId),
  ]) {
    try {
      await refresh();
    } catch (error) {
      console.error(error);
    }
  }
};
