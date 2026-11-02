import { useEffect, useState } from "react";
import type { SingleOrArray, TFilterValue } from "@plane/types";
import { FILTER_FIELD_TYPE } from "@plane/types";
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

/** Value inputs for the EE text / number / number-range filter field types (attribute filters). */
export function AttributeFilterValueInput<V extends TFilterValue>(props: TFilterValueInputProps<string, V>) {
  const { condition, filterFieldConfig, isDisabled, onChange } = props;
  const type = filterFieldConfig?.type;
  const values = Array.isArray(condition.value) ? condition.value.map(String) : [String(condition.value ?? "")];
  const set = (v: string | string[]) => onChange(v as unknown as SingleOrArray<V>);
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
        placeholder={type === FILTER_FIELD_TYPE.TEXT ? "text" : "number"}
        disabled={isDisabled}
        onCommit={set}
      />
    );
  if (type === FILTER_FIELD_TYPE.NUMBER_RANGE) {
    const [from = "", to = ""] = values;
    return wrap(
      <>
        <CommitInput
          type="number"
          value={from}
          placeholder="from"
          disabled={isDisabled}
          onCommit={(v) => set([v, to])}
        />
        <span className="text-placeholder">–</span>
        <CommitInput type="number" value={to} placeholder="to" disabled={isDisabled} onCommit={(v) => set([from, v])} />
      </>
    );
  }
  return null;
}
