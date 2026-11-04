import { describe, expect, it } from "vitest";
import { allowedRoles, defaultRole } from "../allowed-roles";

const a = (requesterProjectRole: number | undefined, requesterIsWorkspaceAdmin: boolean, t: number | null) =>
  allowedRoles({ requesterProjectRole, requesterIsWorkspaceAdmin, targetWorkspaceRole: t });

describe("allowedRoles", () => {
  it("ws admin + project admin, target new or ws member: all roles", () => {
    expect(a(20, true, null)).toEqual([20, 15, 5]);
    expect(a(20, true, 15)).toEqual([20, 15, 5]);
  });
  it("non ws admin never gets role 20, even as project admin", () => {
    expect(a(20, false, null)).toEqual([15, 5]);
  });
  it("capped by the requester's project role", () => {
    expect(a(15, true, null)).toEqual([15, 5]);
    expect(a(5, true, null)).toEqual([5]);
    expect(a(undefined, true, null)).toEqual([5]);
  });
  it("ws admin target can only be project admin", () => {
    expect(a(20, true, 20)).toEqual([20]);
  });
  it("ws admin target + requester not ws admin: nothing allowed", () => {
    expect(a(20, false, 20)).toEqual([]);
  });
  it("ws guest target can only be guest", () => {
    expect(a(20, true, 5)).toEqual([5]);
    expect(a(20, false, 5)).toEqual([5]);
  });
});

describe("defaultRole", () => {
  it("prefers member, else highest, else undefined", () => {
    expect(defaultRole([20, 15, 5])).toBe(15);
    expect(defaultRole([5])).toBe(5);
    expect(defaultRole([20])).toBe(20);
    expect(defaultRole([])).toBeUndefined();
  });
});
