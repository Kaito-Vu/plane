import { describe, expect, it, vi } from "vitest";
import { addMembersAndRefresh } from "../add-members-and-refresh";

const payload = { members: [{ member_id: "u1", role: 15 }] };
const mk = () => {
  const calls: string[] = [];
  const add = vi.fn(async () => void calls.push("add"));
  const refreshWorkspace = vi.fn(async () => void calls.push("ws"));
  const refreshProject = vi.fn(async () => void calls.push("proj"));
  return { calls, deps: { add, refreshWorkspace, refreshProject } };
};

describe("addMembersAndRefresh", () => {
  it("adds once, then refreshes workspace then project", async () => {
    const { calls, deps } = mk();
    const res = await addMembersAndRefresh(deps, { workspaceSlug: "w", projectId: "p", payload });
    expect(deps.add).toHaveBeenCalledTimes(1);
    expect(deps.add).toHaveBeenCalledWith("w", "p", payload);
    expect(calls).toEqual(["add", "ws", "proj"]);
    expect(res).toEqual({ failedRefreshes: [] });
  });
  it("tolerates refresh failures and reports which failed", async () => {
    const { deps } = mk();
    deps.refreshWorkspace.mockRejectedValue(new Error("x"));
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await addMembersAndRefresh(deps, { workspaceSlug: "w", projectId: "p", payload });
    expect(res).toEqual({ failedRefreshes: ["workspace"] });
    expect(deps.refreshProject).toHaveBeenCalled();
    deps.refreshProject.mockRejectedValue(new Error("y"));
    const both = await addMembersAndRefresh(deps, { workspaceSlug: "w", projectId: "p", payload });
    expect(both.failedRefreshes).toEqual(["workspace", "project"]);
    err.mockRestore();
  });
  it("propagates add failure and skips refreshes", async () => {
    const { deps } = mk();
    deps.add.mockRejectedValue({ code: "USER_NOT_ELIGIBLE" });
    await expect(addMembersAndRefresh(deps, { workspaceSlug: "w", projectId: "p", payload })).rejects.toEqual({
      code: "USER_NOT_ELIGIBLE",
    });
    expect(deps.refreshWorkspace).not.toHaveBeenCalled();
    expect(deps.refreshProject).not.toHaveBeenCalled();
  });
});
