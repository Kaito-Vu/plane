import { setToast } from "@plane/blocks/toast";
import { asEeError } from "./work-item-errors";

// ponytail: called from the (hook-less) issue service, so texts are the backend's own
// English messages; move to a hook-based toast if they need translating.

/** Toast backend `warnings` (task/sub-task in a different cycle than its story) after a cycle add. */
export const notifyCycleWarnings = (data: unknown) => {
  const warnings = (data as { warnings?: unknown } | undefined)?.warnings;
  if (!Array.isArray(warnings) || warnings.length === 0) return;
  const [first, ...rest] = warnings.map(String);
  setToast({ type: "warning", title: first, message: rest.join("\n") });
};

/** Toast the EE refusal (e.g. cycle_type_not_allowed for Epic/Feature) of a cycle add. */
export const notifyCycleError = (err: unknown) => {
  const e = asEeError(err);
  if (e) setToast({ type: "error", title: e.message });
};
