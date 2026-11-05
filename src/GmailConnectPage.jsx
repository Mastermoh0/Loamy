import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
    faArrowLeft, faEnvelope, faEnvelopeOpen, faReceipt, faCalendarCheck,
    faBuilding, faFile, faShieldHalved, faRotate, faPlug
} from "@fortawesome/free-solid-svg-icons";
import { isRealUserId, waitForServerSync } from "./services/activitySyncService";
import {
    APP_CALLBACK_URI,
  APP_SCHEME,
    GOOGLE_REDIRECT_URI,
    isNativeApp,
    oauthStateParam,
    parseOAuthState,
} from "./utils/oauth";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// Google OAuth Configuration
const GOOGLE_CLIENT_ID = "72400306293-pnjcf2kqtuli55kdn2l5ouq9qjpgc6kt.apps.googleusercontent.com";
const GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email"
].join(" ");

const GmailConnectPage = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const handledCodeRef = useRef(null);
    
    // State
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [emailsScanned, setEmailsScanned] = useState(0);
    const [transactionsFound, setTransactionsFound] = useState(0);
    const [billsDetected, setBillsDetected] = useState(0);
    const [emailList, setEmailList] = useState([]);
    const [appLinks, setAppLinks] = useState(null);

    useEffect(() => {
        const urlParams = new URLSearchParams(location.search);
        const code = urlParams.get("code");
        const oauthError = urlParams.get("error");
        const { viaApp, kind: stateKind } = parseOAuthState(urlParams.get("state"));

        // The native app sent Google to this https page; hand the result back
        // to the Android app via its custom-scheme deep link.
        if ((code || oauthError) && viaApp && !isNativeApp()) {
            const query = urlParams.toString();
            const schemeUrl = `${APP_CALLBACK_URI}?${query}`;
            // Chrome on Android only reliably opens an app from a script
            // redirect through an intent:// URL; the button below covers the
            // case where Chrome blocks the automatic redirect (no user gesture).
            const intentUrl =
                `intent://gmail-connect?${query}` +
                `#Intent;scheme=${APP_SCHEME};package=${APP_SCHEME};end`;
            const isAndroidBrowser = /android/i.test(navigator.userAgent);
            const target = isAndroidBrowser ? intentUrl : schemeUrl;
            setAppLinks({ target, schemeUrl });
            window.location.replace(target);
            return;
        }

        if (code) {
            if (handledCodeRef.current === code) return;
            handledCodeRef.current = code;
        }

        if (oauthError && !code) {
            window.history.replaceState({}, document.title, "/gmail-connect");
            if (stateKind === "auth") {
                navigate("/?google_error=" + encodeURIComponent("Google sign-in was cancelled."));
            }
            return;
        }

        // "Continue with Google" on Login/Sign Up reuses this page's redirect
        // URI (it's the only one authorized in Google Cloud Console) and tags
        // its request with state=auth. That request happens BEFORE the user
        // has a session, so it must be handled ahead of the session check
        // below, which would otherwise bounce them straight back to "/".
        if (code && stateKind === "auth") {
            window.history.replaceState({}, document.title, "/gmail-connect");
            handleAuthLoginCallback(code);
            return;
        }

        // Check session
        const sessionData = localStorage.getItem("loamy_session");
        if (!sessionData) {
            navigate("/");
            return;
        }

        if (code) {
            handleOAuthCallback(code);
            // Clear the URL params
            window.history.replaceState({}, document.title, "/gmail-connect");
        } else {
            // Check Gmail connection status
            const gmailConnected = localStorage.getItem("gmail_connected") === "true";
            setIsConnected(gmailConnected);

            if (gmailConnected) {
                loadEmailData();
            }
        }
    }, [navigate, location.search]);

    // Handles the "Continue with Google" sign-in/sign-up flow (as opposed to
    // the "Connect Gmail for bank sync" flow this page normally handles).
    const handleAuthLoginCallback = async (code) => {
        setIsLoading(true);
        try {
            const response = await fetch(`${API_URL}/google-auth`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code, redirect_uri: GOOGLE_REDIRECT_URI })
            });
            const data = await response.json();

            if (data.status === "success") {
                // If a DIFFERENT user is signing in on this browser, drop the
                // previous user's cached Gmail connection so they don't see it.
                const prev = JSON.parse(localStorage.getItem("loamy_session") || "{}");
                const hasCachedGmail =
                    localStorage.getItem("gmail_access_token") ||
                    localStorage.getItem("gmail_email_data");
                if (hasCachedGmail && prev.user_id !== data.user_id) {
                    [
                        "gmail_connected", "gmail_email_data", "gmail_access_token",
                        "gmail_refresh_token", "gmail_email", "loamy_last_sync_at",
                    ].forEach((k) => localStorage.removeItem(k));
                }

                localStorage.setItem("loamy_session", JSON.stringify({
                    user_id: data.user_id,
                    email: data.email,
                    name: data.name || data.email?.split("@")[0]
                }));

                // Brand-new Google accounts haven't been through onboarding yet;
                // returning accounts go straight to chat.
                navigate(data.is_new_user ? "/onboarding" : "/chat");
            } else {
                navigate("/?google_error=" + encodeURIComponent(data.error || "Google sign-in failed. Please try again."));
            }
        } catch (error) {
            console.error("Google sign-in error:", error);
            navigate("/?google_error=" + encodeURIComponent("Connection error. Please make sure the backend is running."));
        }
        setIsLoading(false);
    };

    const handleOAuthCallback = async (code) => {
        setIsLoading(true);
        try {
            const response = await fetch(`${API_URL}/gmail/exchange-token`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    code: code,
                    redirect_uri: GOOGLE_REDIRECT_URI
                })
            });
            
            const data = await response.json();
            
            if (data.status === "success") {
                localStorage.setItem("gmail_connected", "true");
                localStorage.setItem("gmail_access_token", data.access_token);
                localStorage.setItem("gmail_email", data.email || "");
                if (data.refresh_token) {
                    localStorage.setItem("gmail_refresh_token", data.refresh_token);
                    // Persist the refresh token on the backend so it can auto-sync
                    // bank data server-side without a live browser token.
                    try {
                        const sess = JSON.parse(localStorage.getItem("loamy_session") || "{}");
                        if (sess.user_id) {
                            await fetch(`${API_URL}/gmail/store-credentials`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ user_id: sess.user_id, refresh_token: data.refresh_token })
                            });
                        }
                    } catch (e) {
                        console.error("[v0] Failed to store Gmail credentials on backend:", e);
                    }
                }
                
                setIsConnected(true);
                
                // Fetch emails immediately
                await fetchEmails(data.access_token);

                // If we arrived here from onboarding, continue to the intended
                // destination (the dashboard) now that Gmail is truly connected
                // and the first sync has run.
                const postRedirect = localStorage.getItem("loamy_post_oauth_redirect");
                if (postRedirect) {
                    localStorage.removeItem("loamy_post_oauth_redirect");
                    setIsLoading(false);
                    navigate(postRedirect);
                    return;
                }
            } else {
                alert("Failed to connect Gmail: " + (data.error || "Unknown error"));
            }
        } catch (error) {
            console.error("OAuth callback error:", error);
            alert("Error connecting Gmail. Please try again.");
        }
        setIsLoading(false);
    };

    // Helper function to refresh expired token
    const refreshAccessToken = async () => {
        const refreshToken = localStorage.getItem("gmail_refresh_token");
        if (!refreshToken) return null;
        
        try {
            const response = await fetch(`${API_URL}/gmail/refresh-token`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            
            const data = await response.json();
            if (data.status === "success" && data.access_token) {
                localStorage.setItem("gmail_access_token", data.access_token);
                return data.access_token;
            }
        } catch (error) {
            console.error("Token refresh failed:", error);
        }
        return null;
    };

    const fetchEmails = async (accessToken) => {
        try {
            // Pass user_id so the backend tracks this user's delta-sync bookmark.
            const sessionData = JSON.parse(localStorage.getItem("loamy_session") || "{}");
            const userId = sessionData.user_id;
            if (!isRealUserId(userId)) return;
            const response = await fetch(`${API_URL}/gmail/fetch-emails`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ access_token: accessToken, user_id: userId })
            });
            
            let data = await response.json();
            if (data.status === "processing") {
                data = await waitForServerSync(userId);
            }
            
            // Check if token expired - try to refresh
            if (data.requires_reauth || data.error === "token_expired" || 
                (data.status === "error" && (data.error?.includes("401") || data.error?.includes("UNAUTHENTICATED")))) {
                const newToken = await refreshAccessToken();
                if (newToken) {
                    // Retry with new token
                    return fetchEmails(newToken);
                } else {
                    // Refresh failed - user needs to reconnect
                    alert("Gmail session expired. Please reconnect your Gmail account.");
                    handleDisconnect();
                    return;
                }
            }
            
            if (data.status === "success" && !data.emails?.length) {
                await loadEmailData();
            } else if (data.status === "success") {
                const emailData = {
                    emails: data.emails,
                    stats: data.stats,
                    total_scanned: data.stats?.emailsScanned || 0
                };
                localStorage.setItem("gmail_email_data", JSON.stringify(emailData));
                displayEmailData(emailData);
            }
        } catch (error) {
            console.error("Error fetching emails:", error);
        }
    };

    const loadEmailData = async () => {
        const cachedData = localStorage.getItem("gmail_email_data");
        if (cachedData) {
            const parsed = JSON.parse(cachedData);
            if (parsed?.emails?.length) {
                displayEmailData(parsed);
                return;
            }
        }
        // Nothing cached (e.g. after disconnect/reconnect): the backend already
        // has this user's stored emails, so show those instead of zeros.
        const sessionData = JSON.parse(localStorage.getItem("loamy_session") || "{}");
        if (!isRealUserId(sessionData.user_id)) return;
        try {
            const res = await fetch(`${API_URL}/gmail/sync-status/${encodeURIComponent(sessionData.user_id)}`);
            let data = await res.json();
            if (data.status === "processing") data = await waitForServerSync(sessionData.user_id);
            if (data.emails?.length) {
                const emailData = {
                    emails: data.emails,
                    stats: data.stats,
                    total_scanned: data.stats?.emailsScanned || data.emails.length
                };
                localStorage.setItem("gmail_email_data", JSON.stringify(emailData));
                displayEmailData(emailData);
            }
        } catch (error) {
            console.error("Error loading stored emails:", error);
        }
    };

    const displayEmailData = (data) => {
        if (data && data.emails) {
            setEmailsScanned(data.total_scanned || data.stats?.emailsScanned || data.emails.length);
            
            // Count transactions and bills (including bank alerts)
            let transactions = 0;
            let bills = 0;
            
            data.emails.forEach(email => {
                // Bank alerts and receipts count as transactions
                if (email.type === "receipt" || email.type === "payment" || 
                    email.type === "bank_alert" || email.type === "bank_debit" || 
                    email.type === "bank_credit" || email.is_bank_alert) {
                    transactions++;
                }
                // Bills and subscriptions
                if (email.type === "bill" || email.type === "subscription") {
                    bills++;
                }
            });
            
            setTransactionsFound(transactions);
            setBillsDetected(bills);
            setEmailList(data.emails.slice(0, 20));
        }
    };

    const handleConnect = () => {
        // Redirect directly to Google OAuth
        const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
            `client_id=${GOOGLE_CLIENT_ID}` +
            `&redirect_uri=${encodeURIComponent(GOOGLE_REDIRECT_URI)}` +
            `&response_type=code` +
            `&scope=${encodeURIComponent(GOOGLE_SCOPES)}` +
            `&access_type=offline` +
            `&prompt=consent` +
            oauthStateParam();
        
        window.location.href = authUrl;
    };

    const handleRefresh = async () => {
        setIsLoading(true);
        
        const accessToken = localStorage.getItem("gmail_access_token");
        if (!accessToken) {
            alert("Not connected to Gmail. Please reconnect.");
            setIsLoading(false);
            return;
        }
        
        try {
            // fetchEmails handles token refresh, background polling and caching.
            await fetchEmails(accessToken);
        } catch (error) {
            console.error("Error fetching emails:", error);
            
            // Show cached data if available
            const cachedData = localStorage.getItem("gmail_email_data");
            if (cachedData) {
                displayEmailData(JSON.parse(cachedData));
                alert("Network error - showing cached data. Try again when connection is stable.");
            } else {
                alert("Network error. Please check your connection and try again.");
            }
        }
        
        setIsLoading(false);
    };

    const handleDisconnect = () => {
        if (window.confirm("Are you sure you want to disconnect Gmail?")) {
            localStorage.removeItem("gmail_connected");
            localStorage.removeItem("gmail_email_data");
            setIsConnected(false);
            setEmailsScanned(0);
            setTransactionsFound(0);
            setBillsDetected(0);
            setEmailList([]);
        }
    };

    const getEmailTypeLabel = (type) => {
        const labels = {
            receipt: "Receipt",
            payment: "Payment",
            bill: "Bill",
            subscription: "Subscription",
            bank: "Bank Alert",
            bank_alert: "Bank Alert",
            bank_debit: "Debit",
            bank_credit: "Credit",
            invoice: "Invoice"
        };
        return labels[type] || "Email";
    };
    
    // Currency symbol helper - supports global currencies
    const getCurrencySymbol = (currency) => {
        const symbols = {
            NGN: "₦",
            USD: "$",
            EUR: "€",
            GBP: "£",
            ZAR: "R",
            KES: "KSh",
            MUR: "Rs",
            INR: "₹",
            GHS: "GH₵",
            XOF: "CFA",
            XAF: "FCFA",
            AED: "د.إ",
            CAD: "C$",
            AUD: "A$",
            JPY: "¥",
            CNY: "¥"
        };
        return symbols[currency] || currency || "$";
    };

    const features = [
        {
            icon: faReceipt,
            title: "Payment Receipts",
            description: "Automatically detect purchase confirmations from Amazon, PayPal, and more"
        },
        {
            icon: faCalendarCheck,
            title: "Subscription Alerts",
            description: "Track recurring payments like Netflix, Spotify, and gym memberships"
        },
        {
            icon: faBuilding,
            title: "Bank Notifications",
            description: "Read transaction alerts from your bank for real-time tracking"
        },
        {
            icon: faFile,
            title: "Bill Reminders",
            description: "Detect utility bills, rent reminders, and payment due dates"
        }
    ];

    if (appLinks) {
        return (
            <div
                className="gmail-container"
                style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, minHeight: "100vh", padding: 24, textAlign: "center" }}
            >
                <h1 style={{ fontSize: 22, margin: 0 }}>Google sign-in complete</h1>
                <p style={{ margin: 0, maxWidth: 320, lineHeight: 1.5 }}>
                    Returning you to the Loamy app. If nothing happens, tap the button below.
                </p>
                <a
                    href={appLinks.target}
                    style={{ padding: "12px 24px", borderRadius: 12, background: "#4aa3f5", color: "#fff", fontWeight: 600, textDecoration: "none" }}
                >
                    Open Loamy
                </a>
            </div>
        );
    }

    const press = "transition-transform active:scale-[0.98]";
    const typeTone = {
        receipt: "bg-loamy-100 text-loamy-700",
        payment: "bg-blue-50 text-blue-700",
        bill: "bg-red-50 text-red-700",
        subscription: "bg-purple-50 text-purple-700",
        invoice: "bg-amber-50 text-amber-700",
    };

    return (
        <div className="flex h-full min-h-0 flex-col bg-canvas font-sans">
            <header className="z-10 flex shrink-0 items-center gap-1 bg-white/80 px-2 pb-2 pt-[calc(env(safe-area-inset-top)+0.5rem)] shadow-sm backdrop-blur-md">
                <button
                    type="button"
                    aria-label="Go back"
                    onClick={() => navigate(window.history.length > 1 ? -1 : "/dashboard")}
                    className={`flex size-11 shrink-0 items-center justify-center rounded-2xl text-loamy-800 ${press}`}
                >
                    <FontAwesomeIcon icon={faArrowLeft} />
                </button>
                <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-loamy-800">Gmail Integration</h1>
            </header>

            <main className="min-h-0 flex-1 overflow-y-auto overscroll-none px-4 pb-8 pt-4">
                <div className="mx-auto flex max-w-2xl flex-col gap-4">
                    <section className={`flex flex-col items-center gap-3 rounded-3xl bg-white p-6 text-center shadow-sm ${press}`}>
                        <div
                            className={`flex size-16 items-center justify-center rounded-full text-2xl ${
                                isConnected ? "bg-loamy-100 text-loamy-700" : "bg-gray-100 text-gray-400"
                            }`}
                        >
                            <FontAwesomeIcon icon={isConnected ? faEnvelopeOpen : faEnvelope} />
                        </div>
                        <h2 className="text-lg font-semibold text-gray-900">
                            {isConnected ? "Gmail Connected" : "Gmail Not Connected"}
                        </h2>
                        <p className="text-sm leading-relaxed text-gray-500">
                            {isConnected
                                ? "Your Gmail is connected. Loamy AI can now analyze your financial emails."
                                : "Connect your Gmail to let Loamy AI analyze your bills, subscriptions, and payment receipts."}
                        </p>
                        {!isConnected && (
                            <button
                                type="button"
                                onClick={handleConnect}
                                className={`flex min-h-12 w-full items-center justify-center gap-3 rounded-2xl bg-white px-5 text-sm font-medium text-gray-800 shadow-sm ring-1 ring-gray-200 ${press}`}
                            >
                                <img src="https://www.google.com/favicon.ico" alt="" className="size-5" />
                                <span>Connect with Google</span>
                            </button>
                        )}
                    </section>

                    {!isConnected && (
                        <section aria-labelledby="gmail-features">
                            <h3 id="gmail-features" className="mb-3 px-1 text-base font-semibold text-gray-900">
                                What Loamy AI Can Access
                            </h3>
                            <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2">
                                {features.map((feature) => (
                                    <div key={feature.title} className={`rounded-3xl bg-white p-4 shadow-sm ${press}`}>
                                        <div className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-loamy-100 text-loamy-700">
                                            <FontAwesomeIcon icon={feature.icon} />
                                        </div>
                                        <h4 className="text-sm font-semibold text-gray-900">{feature.title}</h4>
                                        <p className="mt-1 text-xs leading-relaxed text-gray-500">{feature.description}</p>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {isConnected && (
                        <>
                            <section aria-labelledby="gmail-synced" className="flex flex-col gap-3">
                                <h3 id="gmail-synced" className="px-1 text-base font-semibold text-gray-900">
                                    Synced Email Data
                                </h3>
                                <div className="grid grid-cols-3 gap-3">
                                    {[
                                        [emailsScanned, "Emails Scanned"],
                                        [transactionsFound, "Transactions Found"],
                                        [billsDetected, "Bills Detected"],
                                    ].map(([value, label]) => (
                                        <div
                                            key={label}
                                            className={`flex flex-col items-center justify-center gap-1 rounded-3xl bg-white px-2 py-4 text-center shadow-sm ${press}`}
                                        >
                                            <span className="text-2xl font-bold text-loamy-800">{value}</span>
                                            <span className="text-[11px] leading-tight text-gray-500">{label}</span>
                                        </div>
                                    ))}
                                </div>
                            </section>

                            <section aria-labelledby="gmail-recent" className="rounded-3xl bg-white p-4 shadow-sm">
                                <div className="mb-3 flex items-center justify-between gap-3">
                                    <h4 id="gmail-recent" className="text-base font-semibold text-gray-900">
                                        Recent Financial Emails
                                    </h4>
                                    <button
                                        type="button"
                                        onClick={handleRefresh}
                                        disabled={isLoading}
                                        className={`flex min-h-11 shrink-0 items-center gap-2 rounded-2xl bg-loamy-100 px-4 text-sm font-medium text-loamy-700 disabled:opacity-60 ${press}`}
                                    >
                                        <FontAwesomeIcon icon={faRotate} className={isLoading ? "animate-spin" : ""} />
                                        <span>{isLoading ? "Refreshing…" : "Refresh"}</span>
                                    </button>
                                </div>

                                {emailList.length === 0 ? (
                                    <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-gray-500">
                                        <FontAwesomeIcon icon={faEnvelope} className="text-2xl text-gray-300" />
                                        <p>No financial emails found yet. Tap refresh to scan.</p>
                                    </div>
                                ) : (
                                    <ul className="flex flex-col gap-2">
                                        {emailList.map((email, i) => (
                                            <li key={i} className={`min-w-0 rounded-2xl bg-canvas p-3 ${press}`}>
                                                <p className="truncate text-sm font-semibold text-gray-900">{email.sender}</p>
                                                <p className="mt-0.5 line-clamp-2 break-words text-xs text-gray-500">{email.subject}</p>
                                                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                                                    <span
                                                        className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                                                            typeTone[email.type] || "bg-gray-100 text-gray-600"
                                                        }`}
                                                    >
                                                        {getEmailTypeLabel(email.type)}
                                                    </span>
                                                    {email.amount && (
                                                        <span className="text-sm font-semibold text-loamy-800">
                                                            {getCurrencySymbol(email.currency)}
                                                            {email.amount.toLocaleString(undefined, {
                                                                minimumFractionDigits: 2,
                                                                maximumFractionDigits: 2,
                                                            })}
                                                        </span>
                                                    )}
                                                    <span className="ml-auto text-xs text-gray-500">{email.date}</span>
                                                </div>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </section>

                            <button
                                type="button"
                                onClick={handleDisconnect}
                                className={`flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-red-50 px-5 text-sm font-medium text-red-700 ${press}`}
                            >
                                <FontAwesomeIcon icon={faPlug} />
                                <span>Disconnect Gmail</span>
                            </button>
                        </>
                    )}

                    <aside className="flex gap-3 rounded-3xl bg-loamy-100 p-4 text-loamy-800">
                        <FontAwesomeIcon icon={faShieldHalved} className="mt-0.5 text-lg" />
                        <div>
                            <h4 className="text-sm font-semibold">Your Privacy is Protected</h4>
                            <p className="mt-1 text-xs leading-relaxed text-loamy-800/80">
                                Loamy AI only reads emails related to finances (receipts, bills, bank alerts). We never
                                access personal conversations or store your email content on our servers.
                            </p>
                        </div>
                    </aside>
                </div>
            </main>
        </div>
    );
};

export default GmailConnectPage;
