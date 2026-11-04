import { normalizeQuery, shouldSearch } from "./search-query";
import type { TProjectMemberSearchResult } from "./services/project-member-search.service";

// Adapter for `Select` (infinite mode): the Select debounces (300 ms) and drops stale responses itself.
export const fetchCandidates = async (
  service: { search: (ws: string, projectId: string, q: string) => Promise<TProjectMemberSearchResult[]> },
  workspaceSlug: string,
  projectId: string,
  q: string | undefined
): Promise<{ results: TProjectMemberSearchResult[] }> => {
  if (!shouldSearch(q ?? "")) return { results: [] };
  return { results: await service.search(workspaceSlug, projectId, normalizeQuery(q ?? "")) };
};
