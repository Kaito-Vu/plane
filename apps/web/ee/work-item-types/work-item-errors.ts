import type { TEeError } from "./types";

/** Form-level error keys besides attribute ids. */
export const TYPE_FIELD = "__type";
export const PARENT_FIELD = "__parent";

export const WORK_ITEM_ERROR_CODES = [
  "type_required",
  "type_immutable",
  "parent_required",
  "parent_invalid",
  "parent_type_invalid",
  "parent_cycle",
  "max_depth_exceeded",
  "attribute_required",
  "invalid_value",
  "open_children",
  "cycle_type_not_allowed",
] as const;

export const asEeError = (err: unknown): TEeError | undefined => {
  const e = err as Partial<TEeError> | undefined;
  return e && typeof e === "object" && typeof e.error_code === "string" && typeof e.message === "string"
    ? (e as TEeError)
    : undefined;
};

/** Human message for a backend EE error: i18n per code, falling back to the server message. */
export const workItemErrorMessage = (t: (key: string, params?: Record<string, unknown>) => string, err: unknown) => {
  const e = asEeError(err);
  if (!e) return undefined;
  if (!(WORK_ITEM_ERROR_CODES as readonly string[]).includes(e.error_code)) return e.message;
  if (e.error_code === "open_children") {
    const children = (e.details as { children?: unknown[] } | undefined)?.children;
    return t("agile_work_item.errors.open_children", { count: Array.isArray(children) ? children.length : 0 });
  }
  return t(`agile_work_item.errors.${e.error_code}`);
};

/** Map a backend EE error to form field errors (attribute ids, TYPE_FIELD, PARENT_FIELD). */
export const workItemFieldErrors = (err: unknown): Record<string, string> => {
  const e = asEeError(err);
  if (!e) return {};
  const code = e.error_code;
  if (code === "attribute_required") {
    const missing = (e.details as { missing?: unknown[] } | undefined)?.missing ?? [];
    return Object.fromEntries(missing.map((id) => [String(id), "agile_work_item.errors.field_required"]));
  }
  if (code === "invalid_value") {
    const attr = (e.details as { attribute_id?: unknown } | undefined)?.attribute_id;
    return attr ? { [String(attr)]: "agile_work_item.errors.invalid_value" } : {};
  }
  if (code.startsWith("type_")) return { [TYPE_FIELD]: `agile_work_item.errors.${code}` };
  if (code.startsWith("parent_") || code === "max_depth_exceeded")
    return { [PARENT_FIELD]: `agile_work_item.errors.${code}` };
  return {};
};
