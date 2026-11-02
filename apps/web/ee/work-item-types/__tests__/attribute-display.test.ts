import { describe, expect, it } from "vitest";
import { formatAttributeValue } from "../attribute-display";
import type { TAttribute } from "../types";

const a = (field_type: TAttribute["field_type"], options: TAttribute["options"] = []) => ({ field_type, options });
const names = (id: string) => ({ u1: "Ann" })[id];

describe("formatAttributeValue", () => {
  it("renders empty values as blank", () => {
    expect(formatAttributeValue(a("text"), null, names)).toBe("");
    expect(formatAttributeValue(a("text"), "", names)).toBe("");
  });
  it("renders booleans, options, members and dates", () => {
    const opts = [{ id: "o1", name: "High", sort_order: 0, is_active: true, color: "", is_default: false }];
    expect(formatAttributeValue(a("boolean"), true, names)).toBe("Yes");
    expect(formatAttributeValue(a("boolean"), false, names)).toBe("No");
    expect(formatAttributeValue(a("multi_select", opts), ["o1", "gone"], names)).toBe("High, gone");
    expect(formatAttributeValue(a("member"), "u1", names)).toBe("Ann");
    expect(formatAttributeValue(a("date"), "2026-01-02T00:00:00Z", names)).toBe("2026-01-02");
    expect(formatAttributeValue(a("number"), 5, names)).toBe("5");
  });
});
