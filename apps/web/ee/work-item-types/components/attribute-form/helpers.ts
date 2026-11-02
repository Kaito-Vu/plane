import { setToast } from "@plane/blocks/toast";
import type { TAttribute, TAttributeOption, TAttributeTemplate, TEeError } from "../../types";

export type TAttributeLike = TAttributeTemplate & Partial<Pick<TAttribute, "is_system" | "system_key">>;
type TOptionPayload = Partial<Omit<TAttributeOption, "id">>;

/** Same CRUD surface for workspace templates and project attributes. */
export type TAttributeApi = {
  create: (data: Partial<TAttributeLike>) => Promise<unknown>;
  update: (id: string, data: Partial<TAttributeLike>) => Promise<unknown>;
  remove: (id: string) => Promise<unknown>;
  reorder: (ids: string[], issueTypeId: string) => Promise<unknown>;
  createOption: (id: string, data: TOptionPayload) => Promise<unknown>;
  updateOption: (id: string, optionId: string, data: TOptionPayload) => Promise<unknown>;
  deleteOption: (id: string, optionId: string) => Promise<unknown>;
};

// Backend error_code values that have a dedicated message (agile_attributes.errors.<code>).
const KNOWN_CODES = new Set([
  "duplicate_name",
  "system_attribute_locked",
  "attribute_type_immutable",
  "type_change_blocked",
  "invalid_reorder_ids",
  "invalid_issue_type",
  "issue_type_not_in_project",
  "options_not_allowed",
  "invalid_value",
]);

export const errorMessage = (t: (key: string) => string, err: unknown): string => {
  const e = err as Partial<TEeError> | undefined;
  if (e?.error_code && KNOWN_CODES.has(e.error_code)) return t(`agile_attributes.errors.${e.error_code}`);
  if (e?.message) return e.message;
  // DRF field errors: {field: ["msg"]}
  const first = e && typeof e === "object" ? Object.values(e)[0] : undefined;
  if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  return t("agile_attributes.errors.unknown");
};

/** Run a mutation; on failure toast a readable error and return false. */
export const runWithToast = async (t: (key: string) => string, fn: () => Promise<unknown>): Promise<boolean> => {
  try {
    await fn();
    return true;
  } catch (err) {
    setToast({ type: "error", title: t("agile_attributes.errors.title"), message: errorMessage(t, err) });
    return false;
  }
};
