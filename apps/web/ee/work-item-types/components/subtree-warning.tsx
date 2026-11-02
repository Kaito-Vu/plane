import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@plane/i18n";
import { AttributeService } from "../services/attribute.service";

const service = new AttributeService();

type TProps = {
  projectId: string | null | undefined;
  issueId: string | null | undefined;
  /** Direct child count shown until the subtree count arrives. */
  fallbackCount?: number;
  /** Archive dialog: already-archived descendants are not counted. */
  forArchive?: boolean;
};

/** Delete/archive confirm note: the backend acts on the whole subtree; shows all live descendants. */
export function SubtreeWarning({ projectId, issueId, fallbackCount, forArchive }: TProps) {
  const { t } = useTranslation();
  const { workspaceSlug } = useParams();
  const [count, setCount] = useState<number | undefined>(undefined);
  useEffect(() => {
    if (!workspaceSlug || !projectId || !issueId) return;
    let alive = true;
    service
      .getSubtreeCount(workspaceSlug.toString(), projectId, issueId, forArchive)
      .then((res) => alive && setCount(res.count))
      .catch(console.error);
    return () => {
      alive = false;
    };
  }, [workspaceSlug, projectId, issueId, forArchive]);
  const shown = count ?? fallbackCount;
  if (!shown) return null;
  return (
    <span className="mt-2 block font-medium text-danger-primary">
      {t("agile_work_item.delete_subtree_warning", { count: shown })}
    </span>
  );
}
