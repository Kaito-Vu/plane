import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import { TYPE_KEYS } from "../constants";
import type { TWorkItemTypeKey } from "../types";
import { TypeKeyBadge } from "./type-badge";

type TProps = {
  value: TWorkItemTypeKey | undefined;
  onChange: (key: TWorkItemTypeKey) => void;
  /** Restrict choices (e.g. child types valid for a preset parent). */
  allowed?: TWorkItemTypeKey[];
  /** Type is immutable after create: show it read-only. */
  disabled?: boolean;
  error?: string;
  compact?: boolean;
};

export function TypeSelector({
  value,
  onChange,
  allowed = TYPE_KEYS,
  disabled = false,
  error,
  compact = false,
}: TProps) {
  const { t } = useTranslation();
  if (disabled) return value ? <TypeKeyBadge typeKey={value} /> : null;
  return (
    <div className="flex flex-col gap-1">
      <div role="radiogroup" aria-label={t("agile_work_item.type")} className="flex flex-wrap items-center gap-1">
        {TYPE_KEYS.filter((k) => allowed.includes(k)).map((k) => (
          <button
            key={k}
            type="button"
            role="radio"
            aria-checked={value === k}
            onClick={() => onChange(k)}
            className={cn(
              "rounded-sm p-0.5 opacity-60 hover:opacity-100",
              value === k && "opacity-100 ring-1 ring-accent-strong"
            )}
          >
            <TypeKeyBadge typeKey={k} compact={compact} />
          </button>
        ))}
      </div>
      {error && <span className="text-11 text-danger-primary">{t(error)}</span>}
    </div>
  );
}
