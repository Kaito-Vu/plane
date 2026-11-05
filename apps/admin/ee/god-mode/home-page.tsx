import { useEffect } from "react";
import { observer } from "mobx-react";
import { useSearchParams } from "next/navigation";
import { API_BASE_URL } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import { useInstance } from "@/hooks/store";
import CoreHomePage from "../../app/(all)/(home)/page";

export { meta } from "../../app/(all)/(home)/page";

const SSO_URL = `${API_BASE_URL}/api/god-mode/sso/`;

/** Core sign-in page + "sign in with Entra" + skip login when the web session is already a god-mode one. */
function GodModeHomePage() {
  const { instance, config } = useInstance();
  const hasError = !!useSearchParams().get("error_code");
  const ready = !!instance?.is_setup_done;

  useEffect(() => {
    if (!ready || hasError) return;
    fetch(`${SSO_URL}?check=1`, { credentials: "include" })
      .then((res) => res.json())
      .then((data) => data?.eligible && window.location.assign(SSO_URL))
      .catch(() => undefined);
  }, [ready, hasError]);

  return (
    <>
      <CoreHomePage />
      {ready && config?.is_entra_enabled && (
        <div className="w-full max-w-[22.5rem] pb-6">
          <Button
            type="button"
            variant="secondary"
            size="lg"
            stretch="full"
            label={`Sign in with ${config.entra_provider_name || "Microsoft"}`}
            onClick={() => window.location.assign(SSO_URL)}
          />
        </div>
      )}
    </>
  );
}

export default observer(GodModeHomePage);
