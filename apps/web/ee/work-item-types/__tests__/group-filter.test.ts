import { describe, expect, it, vi } from "vitest";

const attributesByProject: Record<string, { id: string; is_active: boolean }[]> = {};
vi.mock("@/lib/store-context", () => ({ store: { attribute: { attributesByProject } } }));

const { isEeGroupKey, isStaleEeGroupKey, withEeGroupFilter } = await import("../group-filter");

describe("group-filter", () => {
  it("recognises EE group keys", () => {
    expect(isEeGroupKey("type")).toBe(true);
    expect(isEeGroupKey("attribute:abc")).toBe(true);
    expect(isEeGroupKey("state")).toBe(false);
  });

  it("ANDs the group condition into existing rich filters", () => {
    const params: Record<string, unknown> = { filters: JSON.stringify({ priority__in: "high" }) };
    withEeGroupFilter(params, "type", "t1");
    expect(JSON.parse(params.filters as string)).toEqual({ and: [{ priority__in: "high" }, { type__in: "t1" }] });
  });

  it("uses __isnull for the None group and a bare condition when no filters exist", () => {
    const params: Record<string, unknown> = { filters: "{}" };
    withEeGroupFilter(params, "attribute:a1", "None");
    expect(JSON.parse(params.filters as string)).toEqual({ "attribute:a1__isnull": "true" });
  });

  it("flags a stale attribute group key only once attributes are loaded", () => {
    expect(isStaleEeGroupKey("attribute:a1")).toBe(false); // nothing loaded yet
    attributesByProject.p1 = [{ id: "a1", is_active: true }];
    expect(isStaleEeGroupKey("attribute:a1")).toBe(false);
    expect(isStaleEeGroupKey("attribute:gone")).toBe(true);
    expect(isStaleEeGroupKey("type")).toBe(false);
  });
});
