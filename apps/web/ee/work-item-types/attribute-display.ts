import type { TAttribute } from "./types";

/** Human text for an attribute value (list/spreadsheet columns). Pure: member names come from `memberName`. */
export const formatAttributeValue = (
  attribute: Pick<TAttribute, "field_type" | "options">,
  value: unknown,
  memberName: (id: string) => string | undefined
): string => {
  if (value === null || value === undefined || value === "") return "";
  const list = Array.isArray(value) ? value.map(String) : [String(value)];
  switch (attribute.field_type) {
    case "boolean":
      return value === true || value === "true" ? "Yes" : "No";
    case "select":
    case "multi_select":
      return list.map((id) => attribute.options.find((o) => o.id === id)?.name ?? id).join(", ");
    case "member":
    case "multi_member":
      return list.map((id) => memberName(id) ?? id).join(", ");
    case "date":
      return list[0].slice(0, 10);
    case "datetime":
      return new Date(list[0]).toLocaleString();
    default:
      return list.join(", ");
  }
};
