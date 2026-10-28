export type TWorkItemTypeKey = "epic" | "feature" | "user_story" | "task" | "bug" | "sub_task";

export type TAttributeFieldType =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "date"
  | "datetime"
  | "url"
  | "select"
  | "multi_select"
  | "member"
  | "multi_member";

export type TAttributeOption = {
  id: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  color: string;
  is_default: boolean;
};

type TAttributeBase = {
  id: string;
  issue_type: string; // IssueType id
  name: string;
  description: string;
  field_type: TAttributeFieldType;
  is_required: boolean;
  default_value: unknown;
  settings: Record<string, unknown>;
  sort_order: number;
  is_active: boolean;
  options: TAttributeOption[];
};

export type TAttributeTemplate = TAttributeBase;

export type TAttribute = TAttributeBase & {
  is_system: boolean;
  source_template: string | null;
  system_key: string | null;
};

/** attribute id -> value (arrays for multi_select / multi_member) */
export type TAttributeValues = Record<string, unknown>;

/** Flat body of every EE validation error. */
export type TEeError = {
  error_code: string;
  message: string;
  details?: unknown;
};
