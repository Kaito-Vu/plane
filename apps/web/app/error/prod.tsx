/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { Button } from "@makeplane/propel/components/button";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";
// layouts
import DefaultLayout from "@/layouts/default-layout";

// Production Error Component
interface ProdErrorComponentProps {
  onGoHome: () => void;
  onReload: () => void;
}

export function ProdErrorComponent({ onGoHome, onReload }: ProdErrorComponentProps) {
  return (
    <DefaultLayout>
      {/* The blocks illustration is themed through CSS tokens, so no theme lookup is needed here. */}
      <div className="size-full px-6">
        <EmptyStateDetailed
          align="center"
          assetKey="server-error"
          assetClassName="size-40"
          title="🚧 Looks like something went wrong!"
          description="We track these errors automatically and working on getting things back up and running. In the meantime, try refreshing."
          customButton={
            <div className="flex flex-col items-center gap-4">
              <div className="flex flex-col gap-4 sm:flex-row">
                <Button variant="primary" size="lg" stretch="auto" label="Reload" onClick={onReload} />
                <Button variant="secondary" size="lg" stretch="auto" label="Go to home" onClick={onGoHome} />
              </div>
            </div>
          }
        />
      </div>
    </DefaultLayout>
  );
}
