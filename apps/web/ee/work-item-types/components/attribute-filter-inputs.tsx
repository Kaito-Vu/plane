import { useEffect, useState } from "react";
import type { SingleOrArray, TFilterValue } from "@plane/types";
import { FILTER_FIELD_TYPE } from "@plane/types";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import { COMMON_FILTER_ITEM_BORDER_CLASSNAME } from "@/components/rich-filters/shared";
import type { TFilterValueInputProps } from "@/components/rich-filters/shared";

const INPUT = "h-full w-28 bg-transparent px-2 text-body-xs-regular outline-none placeholder:text-placeholder";

/** Commits on blur / Enter so typing does not refetch the list on every keystroke. */
function CommitInput(props: {
  value: string;
  type: "text" | "number";
  placeholder: string;
  disabled?: boolean;
  onCommit: (value: string) => void;
}) {
  const { value, type, placeholder, disabled, onCommit } = props;
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => draft !== value && onCommit(draft.trim());
  return (
    <input
      type={type}
      step="any"
      aria-label={placeholder}
      className={INPUT}
      value={draft}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && commit()}
    />
  );
}

const EE_TYPES = new Set<string>([FILTER_FIELD_TYPE.TEXT, FILTER_FIELD_TYPE.NUMBER, FILTER_FIELD_TYPE.NUMBER_RANGE]);

/** True for the EE field types this file renders (lets the core switch render it as a component). */
export const isAttributeFilterFieldType = (type: string | undefined) => !!type && EE_TYPES.has(type);

/** Both ends of a between range, kept locally until complete: the backend rejects "5," with a 400. */
function NumberRangeInput(props: {
  values: string[];
  disabled?: boolean;
  onCommit: (v: string[] | undefined) => void;
}) {
  const { values, disabled, onCommit } = props;
  const { t } = useTranslation();
  const [range, setRange] = useState<[string, string]>([values[0] ?? "", values[1] ?? ""]);
  const [from0, to0] = values;
  useEffect(() => setRange([from0 ?? "", to0 ?? ""]), [from0, to0]);
  const update = (index: 0 | 1, v: string) => {
    const next: [string, string] = index === 0 ? [v, range[1]] : [range[0], v];
    setRange(next);
    if (next[0] && next[1]) onCommit(next);
    else if (!next[0] && !next[1]) onCommit(undefined); // cleared: drop the condition
    // one end only: no filter value yet, nothing is sent
  };
  return (
    <>
      <CommitInput
        type="number"
        value={range[0]}
        placeholder={t("agile_work_item.filter.from")}
        disabled={disabled}
        onCommit={(v) => update(0, v)}
      />
      <span className="text-placeholder">–</span>
      <CommitInput
        type="number"
        value={range[1]}
        placeholder={t("agile_work_item.filter.to")}
        disabled={disabled}
        onCommit={(v) => update(1, v)}
      />
    </>
  );
}

/** Value inputs for the EE text / number / number-range filter field types (attribute filters).
 * Empty or incomplete values are never sent: "" drops the condition, half a range waits for the other end. */
export function AttributeFilterValueInput<V extends TFilterValue>(props: TFilterValueInputProps<string, V>) {
  const { condition, filterFieldConfig, isDisabled, onChange } = props;
  const { t } = useTranslation();
  const type = filterFieldConfig?.type;
  const values = Array.isArray(condition.value)
    ? condition.value.map(String)
    : condition.value === null || condition.value === undefined
      ? []
      : [String(condition.value)];
  const set = (v: string | string[] | undefined) => onChange(v as unknown as SingleOrArray<V>);
  const wrap = (children: React.ReactNode) => (
    <div className={cn("flex h-full items-center", { [COMMON_FILTER_ITEM_BORDER_CLASSNAME]: !isDisabled })}>
      {children}
    </div>
  );
  if (type === FILTER_FIELD_TYPE.TEXT || type === FILTER_FIELD_TYPE.NUMBER)
    return wrap(
      <CommitInput
        type={type === FILTER_FIELD_TYPE.TEXT ? "text" : "number"}
        value={values[0] ?? ""}
        placeholder={t(
          type === FILTER_FIELD_TYPE.TEXT ? "agile_work_item.filter.text" : "agile_work_item.filter.number"
        )}
        disabled={isDisabled}
        onCommit={(v) => set(v === "" ? undefined : v)}
      />
    );
  if (type === FILTER_FIELD_TYPE.NUMBER_RANGE)
    return wrap(<NumberRangeInput values={values} disabled={isDisabled} onCommit={set} />);
  return null;
}
