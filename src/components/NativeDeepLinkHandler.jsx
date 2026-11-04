import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { App as CapacitorApp } from "@capacitor/app";
import { APP_SCHEME, isNativeApp, parseCallbackParams } from "../utils/oauth";

// Catches com.loamy.app://... links (the Google OAuth callback) and routes
// them into the matching in-app page with the code/tokens as query params.
export default function NativeDeepLinkHandler() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!isNativeApp()) return undefined;

    let removed = false;
    let handle = null;

    CapacitorApp.addListener("appUrlOpen", ({ url }) => {
      if (!url || !url.startsWith(`${APP_SCHEME}://`)) return;

      const withoutScheme = url.slice(`${APP_SCHEME}://`.length);
      const path = withoutScheme.split(/[?#]/)[0].replace(/\/+$/, "");
      const params = parseCallbackParams(url);
      const query = params.toString();

      navigate(`/${path || "gmail-connect"}${query ? `?${query}` : ""}`, { replace: true });
    }).then((listener) => {
      if (removed) listener.remove();
      else handle = listener;
    });

    return () => {
      removed = true;
      if (handle) handle.remove();
    };
  }, [navigate]);

  return null;
}
