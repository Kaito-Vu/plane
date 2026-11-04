import { describe, expect, it } from "vitest";
import { normalizeQuery, shouldSearch } from "../search-query";

describe("search-query", () => {
  it("requires at least 3 chars after trim", () => {
    expect(shouldSearch("ab")).toBe(false);
    expect(shouldSearch("abc")).toBe(true);
    expect(shouldSearch("  ab  ")).toBe(false);
  });
  it("trims the query", () => {
    expect(normalizeQuery("  A@b.c ")).toBe("A@b.c");
  });
});
