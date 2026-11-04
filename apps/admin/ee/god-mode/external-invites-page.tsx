/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { Switch } from "@makeplane/propel/components/switch";
import { godModeService as instanceService } from "./service";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
import { Skeleton } from "@plane/blocks/skeleton";

const ExternalInvitesPage = observer(function ExternalInvitesPage() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data, error, isLoading, mutate } = useSWR("EXTERNAL_INVITES", () => instanceService.getExternalInvites());

  const handleToggle = async (enabled: boolean) => {
    setIsSubmitting(true);
    try {
      const res = await instanceService.setExternalInvites(enabled);
      await mutate(res, { revalidate: false });
      setToast({
        type: "success",
        title: "Success",
        message: `External invitations ${res.enabled ? "enabled" : "disabled"}.`,
      });
    } catch (e: any) {
      setToast({ type: "error", title: "Error", message: e?.error ?? "Failed to update the setting." });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PageWrapper
      header={{
        title: "External invitations",
        description: (
          <>
            When off, no email invitations can be sent or accepted: users can only enter through the identity provider
            (such as Entra ID) or with existing accounts, and project admins can still add existing users.
            {error && <div className="text-13 font-regular text-danger-primary">Failed to load the setting.</div>}
          </>
        ),
        actions:
          isLoading || error ? (
            <Skeleton>
              <Skeleton.Item width="24px" height="16px" className="rounded-full" />
            </Skeleton>
          ) : (
            <Switch
              aria-label="Enable external invitations"
              checked={!!data?.enabled}
              onCheckedChange={handleToggle}
              size="sm"
              disabled={isSubmitting}
            />
          ),
      }}
    >
      {null}
    </PageWrapper>
  );
});

export const meta = () => [{ title: "External invitations - God Mode" }];

export default ExternalInvitesPage;
