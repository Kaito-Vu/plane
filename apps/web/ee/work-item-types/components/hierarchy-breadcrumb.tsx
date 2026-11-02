import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useTranslation } from "@plane/i18n";
import type { TIssue } from "@plane/types";
import { generateWorkItemLink } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { IssueService } from "@/services/issue";
import { TypeBadge } from "./type-badge";

const issueService = new IssueService();
// ponytail: matches backend max depth (10); stops runaway loops on bad data
const MAX_DEPTH = 10;

type TProps = { workspaceSlug: string; projectId: string; issueId: string };

/** Ancestor chain (root → direct parent) of an issue; missing ancestors are fetched once. */
export const HierarchyBreadcrumb = observer(function HierarchyBreadcrumb({
  workspaceSlug,
  projectId,
  issueId,
}: TProps) {
  const { t } = useTranslation();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const { getProjectById } = useProject();
  const [fetched, setFetched] = useState<Record<string, TIssue>>({});
  const find = (id: string) => getIssueById(id) ?? fetched[id];

  const chain: TIssue[] = [];
  let missing: string | undefined;
  let cursor = find(issueId)?.parent_id;
  while (cursor && chain.length < MAX_DEPTH) {
    const node = find(cursor);
    if (!node) {
      missing = cursor;
      break;
    }
    chain.unshift(node);
    cursor = node.parent_id;
  }

  useEffect(() => {
    if (!missing) return;
    const id = missing;
    issueService
      .retrieve(workspaceSlug, projectId, id)
      .then((res) => setFetched((prev) => ({ ...prev, [id]: res })))
      .catch(console.error);
  }, [missing, workspaceSlug, projectId]);

  if (chain.length === 0) return null;
  const identifier = getProjectById(projectId)?.identifier ?? "";
  return (
    <nav aria-label={t("agile_work_item.ancestors")} className="flex flex-wrap items-center gap-1 text-12">
      {chain.map((node, i) => (
        <span key={node.id} className="flex items-center gap-1">
          {i > 0 && <span className="text-tertiary">/</span>}
          <TypeBadge projectId={projectId} typeId={node.type_id} compact />
          <Link
            className="max-w-48 truncate text-secondary hover:text-primary hover:underline"
            href={generateWorkItemLink({
              workspaceSlug,
              projectId,
              issueId: node.id,
              projectIdentifier: identifier,
              sequenceId: node.sequence_id,
            })}
          >
            {identifier}-{node.sequence_id} {node.name}
          </Link>
        </span>
      ))}
    </nav>
  );
});
