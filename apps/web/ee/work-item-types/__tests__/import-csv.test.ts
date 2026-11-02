import { describe, expect, it } from "vitest";
import { csvToImportRows, parseCsv } from "../import-csv";
import type { TAttribute } from "../types";

const attr = (over: Partial<TAttribute>): TAttribute =>
  ({ id: "a1", issue_type: "bug-id", name: "Severity", field_type: "select", options: [], ...over }) as TAttribute;

const typeIdOf = (k: string) => (k === "bug" ? "bug-id" : undefined);

describe("parseCsv", () => {
  it("handles quotes, escaped quotes, CRLF, BOM and blank lines", () => {
    expect(parseCsv('﻿a,b\r\n"x, y","he said ""hi"""\n\n1,\n')).toEqual([
      ["a", "b"],
      ["x, y", 'he said "hi"'],
      ["1", ""],
    ]);
  });
});

describe("csvToImportRows", () => {
  const severity = attr({
    options: [{ id: "opt-major", name: "Major", sort_order: 0, is_active: true, color: "", is_default: false }],
  });
  const tags = attr({ id: "a2", name: "Tags", field_type: "multi_select", options: [] });
  const points = attr({ id: "a3", name: "Points", field_type: "number" });

  it("maps known columns, attribute columns of the row type and passes the rest through", () => {
    const rows = csvToImportRows(
      parseCsv("ref,type,name,severity,Tags,Points,priority\nb1,bug,Crash,major,x; y,3,high\n"),
      [severity, tags, points],
      typeIdOf
    );
    expect(rows).toEqual([
      {
        ref: "b1",
        type: "bug",
        name: "Crash",
        priority: "high",
        attribute_values: { a1: "opt-major", a2: ["x", "y"], a3: 3 },
      },
    ]);
  });

  it("numbers rows without a ref and ignores attributes of other types", () => {
    const rows = csvToImportRows(parseCsv("type,name,Severity\ntask,T,Major\n"), [severity], typeIdOf);
    expect(rows).toEqual([{ type: "task", name: "T", Severity: "Major", ref: "1" }]);
  });
});
