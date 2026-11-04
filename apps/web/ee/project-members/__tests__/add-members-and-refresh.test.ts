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
    await addMembersAndRefresh(deps, { workspaceSlug: "w", projectId: "p", payload });
    expect(deps.add).toHaveBeenCalledTimes(1);
    expect(deps.add).toHaveBeenCalledWith("w", "p", payload);
    expect(calls).toEqual(["add", "ws", "proj"]);
  });
  it("tolerates refresh failures", async () => {
    const { deps } = mk();
    deps.refreshWorkspace.mockRejectedValue(new Error("x"));
    deps.refreshProject.mockRejectedValue(new Error("y"));
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    await expect(addMembersAndRefresh(deps, { workspaceSlug: "w", projectId: "p", payload })).resolves.toBeUndefined();
    expect(deps.refreshProject).toHaveBeenCalled();
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
