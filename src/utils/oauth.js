import { Capacitor } from "@capacitor/core";

export const APP_SCHEME = "com.loamy.app";
export const APP_CALLBACK_URI = `${APP_SCHEME}://gmail-connect`;

export const isNativeApp = () => Capacitor.isNativePlatform();

// Google only accepts http(s) redirect URIs for "Web application" OAuth
// clients, so a raw custom-scheme redirect is rejected unless the client is
// configured for it. When VITE_PUBLIC_WEB_URL is set (e.g. https://app.loamy.com),
// the native app sends Google to <that url>/gmail-connect (already whitelisted),
// and that page immediately forwards the result to com.loamy.app://gmail-connect.
// When it is not set, the native app uses the custom scheme directly.
const PUBLIC_WEB_URL = (import.meta.env.VITE_PUBLIC_WEB_URL || "").replace(/\/+$/, "");

export const usesWebBounce = () => isNativeApp() && Boolean(PUBLIC_WEB_URL);

export const getGoogleRedirectUri = () => {
    if (!isNativeApp()) return window.location.origin + "/gmail-connect";
    return PUBLIC_WEB_URL ? `${PUBLIC_WEB_URL}/gmail-connect` : APP_CALLBACK_URI;
};

export const GOOGLE_REDIRECT_URI = getGoogleRedirectUri();

// OAuth "state" values: "auth" marks the Continue-with-Google sign-in flow.
// Requests that must be bounced back into the app are prefixed with "app".
export const oauthStateParam = (kind) => {
    const bounce = usesWebBounce();
    if (!kind && !bounce) return "";
    const value = bounce ? (kind ? `app:${kind}` : "app") : kind;
    return `&state=${encodeURIComponent(value)}`;
};

export const parseOAuthState = (state) => {
    const raw = state || "";
    const viaApp = raw === "app" || raw.startsWith("app:");
    const kind = viaApp ? raw.slice(4) : raw;
    return { viaApp, kind: kind || null };
};

// Merges ?query and #hash parameters of a (possibly custom-scheme) URL.
export const parseCallbackParams = (rawUrl) => {
    const params = new URLSearchParams();
    const queryStart = rawUrl.indexOf("?");
    const hashStart = rawUrl.indexOf("#");
    if (queryStart !== -1) {
        const end = hashStart !== -1 && hashStart > queryStart ? hashStart : rawUrl.length;
        new URLSearchParams(rawUrl.slice(queryStart + 1, end)).forEach((v, k) => params.set(k, v));
    }
    if (hashStart !== -1) {
        new URLSearchParams(rawUrl.slice(hashStart + 1)).forEach((v, k) => params.set(k, v));
    }
    return params;
};
