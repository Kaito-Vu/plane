/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { godModeService as instanceService } from "./service";
import type { IInstanceAdmin } from "@plane/types";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
// hooks
import { useUser } from "@/hooks/store";
// types

const AdminAccessPage = observer(function AdminAccessPage() {
  const { currentUser } = useUser();
  // states
  const [email, setEmail] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [toRemove, setToRemove] = useState<IInstanceAdmin | null>(null);
  const [isRemoving, setIsRemoving] = useState(false);
  // fetch
  const { data: admins, mutate } = useSWR("INSTANCE_ADMINS", () => instanceService.admins());

  const handleAdd = async () => {
    if (!email.trim()) return;
    setIsAdding(true);
    try {
      await instanceService.addAdmin(email.trim());
      setEmail("");
      await mutate();
      setToast({ type: "success", title: "Success", message: "God-mode access granted." });
    } catch (error: any) {
      setToast({ type: "error", title: "Error", message: error?.error ?? "Failed to grant access." });
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemove = async () => {
    if (!toRemove) return;
    setIsRemoving(true);
    try {
      await instanceService.removeAdmin(toRemove.id);
      setToRemove(null);
      await mutate();
      setToast({ type: "success", title: "Success", message: "God-mode access revoked." });
    } catch (error: any) {
      setToast({ type: "error", title: "Error", message: error?.error ?? "Failed to revoke access." });
    } finally {
      setIsRemoving(false);
    }
  };

  return (
    <PageWrapper
      header={{
        title: "Admin access",
        description: "Only the users listed here can sign in to God Mode and change instance settings.",
      }}
    >
      <ConfirmDialog
        isOpen={!!toRemove}
        handleClose={() => setToRemove(null)}
        handleSubmit={handleRemove}
        isSubmitting={isRemoving}
        variant="danger"
        title="Revoke access"
        content={`${toRemove?.user_detail?.email ?? "This user"} will no longer be able to access God Mode.`}
        primaryButtonText={{ loading: "Revoking", default: "Revoke" }}
      />
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="text-16 font-medium">Grant access</div>
          <div className="text-11 text-tertiary">The user must already have a Plane account.</div>
          <div className="flex items-center gap-2">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              size="lg"
              placeholder="user@company.com"
            />
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label="Add"
              loading={isAdding}
              disabled={!email.trim()}
              onClick={handleAdd}
            />
          </div>
        </div>
        <div className="space-y-2">
          <div className="text-16 font-medium">
            Superadmins <span className="text-tertiary">• {admins?.length ?? 0}</span>
          </div>
          <div className="flex flex-col gap-2">
            {admins?.map((admin) => {
              const isSelf = admin.user === currentUser?.id;
              return (
                <div
                  key={admin.id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-subtle bg-layer-1 p-3"
                >
                  <div className="min-w-0">
                    <div className="truncate text-14 font-medium">
                      {admin.user_detail?.display_name || admin.user_detail?.email}
                      {isSelf && <span className="ml-2 text-11 text-tertiary">(you)</span>}
                    </div>
                    <div className="truncate text-11 text-tertiary">{admin.user_detail?.email}</div>
                  </div>
                  <Button
                    variant="danger"
                    size="sm"
                    stretch="auto"
                    label="Revoke"
                    disabled={isSelf}
                    onClick={() => setToRemove(admin)}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </PageWrapper>
  );
});

export const meta = () => [{ title: "Admin access - God Mode" }];

export default AdminAccessPage;
