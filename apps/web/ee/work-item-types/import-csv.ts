import type { TAttribute } from "./types";

/** RFC 4180-ish CSV: quoted fields, "" escapes, CRLF/LF. Returns rows of cells; blank lines dropped. */
export const parseCsv = (text: string): string[][] => {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const src = text.replace(/^﻿/, "");
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (quoted) {
      if (c === '"' && src[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(cell);
      cell = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && src[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some((v) => v !== "")) rows.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  row.push(cell);
  if (row.some((v) => v !== "")) rows.push(row);
  return rows;
};

const KNOWN = new Set(["ref", "type", "parent_ref", "parent_id", "name"]);

/**
 * CSV records -> import row payloads. Known columns map 1:1; a column named like an attribute of the row's
 * type goes to attribute_values (select options matched by name, multi values split on ";"); the rest
 * (description_html, priority, ...) is passed through to the issue serializer.
 */
export const csvToImportRows = (
  table: string[][],
  attributes: TAttribute[],
  typeIdOf: (typeKey: string) => string | undefined
): Record<string, unknown>[] => {
  const [header = [], ...records] = table;
  const cols = header.map((h) => h.trim());
  return records.map((record, index) => {
    const row: Record<string, unknown> = {};
    const values: Record<string, unknown> = {};
    const raw = Object.fromEntries(cols.map((c, i) => [c, (record[i] ?? "").trim()]));
    const typeId = typeIdOf(raw.type ?? "");
    for (const [col, value] of Object.entries(raw)) {
      if (value === "") continue;
      if (KNOWN.has(col)) {
        row[col] = value;
        continue;
      }
      const attr = attributes.find((a) => a.issue_type === typeId && a.name.toLowerCase() === col.toLowerCase());
      if (!attr) row[col] = value;
      else values[attr.id] = attributeValue(attr, value);
    }
    row.ref ??= String(index + 1);
    if (Object.keys(values).length) row.attribute_values = values;
    return row;
  });
};

const attributeValue = (attr: TAttribute, value: string): unknown => {
  const option = (v: string) => attr.options.find((o) => o.name.toLowerCase() === v.toLowerCase())?.id ?? v;
  switch (attr.field_type) {
    case "number":
      return Number(value);
    case "boolean":
      return ["true", "yes", "1"].includes(value.toLowerCase());
    case "select":
      return option(value);
    case "multi_select":
      return value.split(";").map((v) => option(v.trim()));
    case "multi_member":
      return value.split(";").map((v) => v.trim());
    default:
      return value;
  }
};
