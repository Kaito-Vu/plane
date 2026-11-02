import { useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import useSWR from "swr";
import { useTranslation } from "@plane/i18n";
import { generateWorkItemLink } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { TYPE_KEYS } from "../constants";
import { useAttributes } from "../hooks/use-attributes";
import { TypeBadge, TypeKeyBadge } from "./type-badge";

type TNodeProps = { workspaceSlug: string; projectId: string; issueId: string; depth: number };

const useChildren = (workspaceSlug: string, projectId: string, issueId: string, enabled: boolean) => {
  const {
    fetchSubIssues,
    subIssues: { subIssuesByIssueId },
  } = useIssueDetail();
  useSWR(enabled ? `EE_CHILDREN_TREE_${issueId}` : null, () => fetchSubIssues(workspaceSlug, projectId, issueId));
  return subIssuesByIssueId(issueId) ?? [];
};

const ChildNode = observer(function ChildNode({ workspaceSlug, projectId, issueId, depth }: TNodeProps) {
  const [open, setOpen] = useState(false);
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const { getProjectById } = useProject();
  const children = useChildren(workspaceSlug, projectId, issueId, open);
  const issue = getIssueById(issueId);
  if (!issue) return null;
  const identifier = getProjectById(issue.project_id ?? projectId)?.identifier ?? "";
  const hasChildren = (issue.sub_issues_count ?? 0) > 0;
  return (
    <li>
      <div className="flex items-center gap-2 py-0.5 text-13" style={{ paddingLeft: depth * 16 }}>
        <button
          type="button"
          aria-expanded={open}
          disabled={!hasChildren}
          onClick={() => setOpen((v) => !v)}
          className="w-4 text-tertiary disabled:invisible"
        >
          {open ? "▾" : "▸"}
        </button>
        <TypeBadge projectId={projectId} typeId={issue.type_id} compact />
        <Link
          className="truncate hover:underline"
          href={generateWorkItemLink({
            workspaceSlug,
            projectId,
            issueId,
            projectIdentifier: identifier,
            sequenceId: issue.sequence_id,
          })}
        >
          <span className="text-tertiary">
            {identifier}-{issue.sequence_id}
          </span>{" "}
          {issue.name}
        </Link>
      </div>
      {open && children.length > 0 && (
        <ul>
          {children.map((id) => (
            <ChildNode key={id} workspaceSlug={workspaceSlug} projectId={projectId} issueId={id} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
});

type TProps = { workspaceSlug: string; projectId: string; issueId: string };

/** Direct children grouped by type; each child expands lazily into its own subtree. */
export const ChildrenTree = observer(function ChildrenTree({ workspaceSlug, projectId, issueId }: TProps) {
  const { t } = useTranslation();
  const { getTypeKey } = useAttributes();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const children = useChildren(workspaceSlug, projectId, issueId, true);
  if (children.length === 0) return null;
  const typeOf = (id: string) => getTypeKey(projectId, getIssueById(id)?.type_id);
  const groups = TYPE_KEYS.map((k) => ({ key: k, ids: children.filter((id) => typeOf(id) === k) })).filter(
    (g) => g.ids.length > 0
  );
  const untyped = children.filter((id) => !typeOf(id));
  return (
    <section className="flex flex-col gap-2">
      <h4 className="text-13 font-medium text-secondary">
        {t("agile_work_item.children")} ({children.length})
      </h4>
      {groups.map((g) => (
        <div key={g.key} className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <TypeKeyBadge typeKey={g.key} />
            <span className="text-12 text-tertiary">{g.ids.length}</span>
          </div>
          <ul>
            {g.ids.map((id) => (
              <ChildNode key={id} workspaceSlug={workspaceSlug} projectId={projectId} issueId={id} depth={0} />
            ))}
          </ul>
        </div>
      ))}
      {untyped.length > 0 && (
        <ul>
          {untyped.map((id) => (
            <ChildNode key={id} workspaceSlug={workspaceSlug} projectId={projectId} issueId={id} depth={0} />
          ))}
        </ul>
      )}
    </section>
  );
});
