import { useTranslation } from "@plane/i18n";

/** Delete/archive confirm note: the backend removes the whole subtree. Only direct child count is known client-side. */
export function SubtreeWarning({ count }: { count: number | undefined }) {
  const { t } = useTranslation();
  if (!count) return null;
  return (
    <span className="mt-2 block font-medium text-danger-primary">
      {t("agile_work_item.delete_subtree_warning", { count })}
    </span>
  );
}
