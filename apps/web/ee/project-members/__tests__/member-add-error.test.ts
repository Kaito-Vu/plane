import { describe, expect, it } from "vitest";
import { memberAddErrorKey } from "../member-add-error";

const K = "project_settings.members.invite_members.errors";

describe("memberAddErrorKey", () => {
  it("maps backend codes", () => {
    expect(memberAddErrorKey({ code: "USER_NOT_ELIGIBLE", error: "x" })).toBe(`${K}.not_eligible`);
    expect(memberAddErrorKey({ code: "ALREADY_MEMBER" })).toBe(`${K}.already_member`);
    expect(memberAddErrorKey({ code: "ROLE_NOT_ALLOWED" })).toBe(`${K}.role_not_allowed`);
  });
  it("maps the uncoded 400s", () => {
    expect(memberAddErrorKey({ error: "Invalid role" })).toBe(`${K}.role_not_allowed`);
    expect(memberAddErrorKey({ error: "You cannot add a user with role higher than the workspace role" })).toBe(
      `${K}.role_conflict`
    );
    expect(memberAddErrorKey({ error: "You cannot add a user with role lower than the workspace role" })).toBe(
      `${K}.role_conflict`
    );
  });
  it("falls back to generic", () => {
    expect(memberAddErrorKey({ error: "boom" })).toBe(`${K}.generic`);
    expect(memberAddErrorKey(undefined)).toBe(`${K}.generic`);
    expect(memberAddErrorKey(new Error("net"))).toBe(`${K}.generic`);
  });
});
