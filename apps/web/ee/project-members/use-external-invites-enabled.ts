import { useEffect, useState } from "react";
import { makeCachedLoader } from "./invites-cache";
import { projectMemberSearchService } from "./services/project-member-search.service";

// Fetched once per page load on success; a failure is not cached (retried on next mount). False until known.
const load = makeCachedLoader(() => projectMemberSearchService.externalInvitesEnabled());

export const useExternalInvitesEnabled = (): boolean => {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let active = true;
    load()
      .then((v) => active && setEnabled(v))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);
  return enabled;
};
