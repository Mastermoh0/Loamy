import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { lazy, Suspense } from "react";
const BusinessWorkspace = lazy(() => import('./BusinessWorkspace.jsx'));
const CustomerInvoice = lazy(() => import('./CustomerInvoice.jsx'));
const enterpriseEnabled = import.meta.env.DEV || import.meta.env.VITE_ENTERPRISE_ENABLED === 'true';
const enterpriseOnly = import.meta.env.VITE_ENTERPRISE_ONLY === 'true';

// Pages
import Login from "./Login.jsx";
import SignUp from "./SignUp.jsx";
import Dashboard from "./Dashboard.jsx";
import ChatPage from "./ChatPage.jsx";
import GmailConnectPage from "./GmailConnectPage.jsx";
import InvoicesPage from "./InvoicesPage.jsx";
import ReviewQueuePage from "./ReviewQueuePage.jsx";
import OnboardingWizard from "./OnboardingWizard.jsx";
import SettingsPage from "./SettingsPage.jsx";
import AccountDetail from "./pages/AccountDetail.jsx";
import AllAccountsOverview from "./pages/AllAccountsOverview.jsx";

import MobileNav from "./components/MobileNav.jsx";
import NativeDeepLinkHandler from "./components/NativeDeepLinkHandler.jsx";

// Global activity-driven sync. Wrapping the whole app (rather than a single
// page) means ANY interaction anywhere can trigger an automatic bank sync.
import { useGlobalActivitySync } from "./hooks/useGlobalActivitySync";

export default function App() {
  const { pathname } = useLocation();
  // The backend enforces the 5-minute cooldown, so it's safe to keep this on
  // app-wide; the hook just debounces and pings.
  useGlobalActivitySync({ enabled: !enterpriseOnly && pathname !== '/business' && pathname !== '/customer-invoice', debounceMs: 2000 });

  if (enterpriseOnly || (enterpriseEnabled && pathname === '/customer-invoice')) return <div className="flex h-dvh flex-col overflow-hidden bg-canvas"><main id="app-main" className="min-h-0 flex-1 overflow-y-auto"><Suspense fallback={<p>Opening business workspace…</p>}><Routes><Route path="/business" element={<BusinessWorkspace />} /><Route path="/customer-invoice" element={<CustomerInvoice />} /><Route path="*" element={<Navigate to="/business" replace />} /></Routes></Suspense></main></div>;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas">
    <NativeDeepLinkHandler />
    <main id="app-main" className="min-h-0 flex-1 overflow-y-auto overscroll-none">
    <Routes>
      {/* Auth Routes */}
      <Route path="/" element={<Login />} />
      {enterpriseEnabled && <Route path="/business" element={<Suspense fallback={<p>Opening business workspace…</p>}><BusinessWorkspace /></Suspense>} />}
      <Route path="/onboarding" element={<OnboardingWizard />} />
      <Route path="/signup" element={<SignUp />} />

      {/* Main App Routes */}
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/chat" element={<ChatPage />} />
      {/* Savings & Goals is hidden from the UI for now; send any deep links
          or bookmarks straight to the dashboard instead of a dead page. */}
      <Route path="/goals" element={<Navigate to="/dashboard" replace />} />
      <Route path="/gmail-connect" element={<GmailConnectPage />} />
      <Route path="/invoices" element={<InvoicesPage />} />
      <Route path="/review-queue" element={<ReviewQueuePage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/accounts" element={<AllAccountsOverview />} />
      <Route path="/accounts/:accountId" element={<AccountDetail />} />

      {/* Aliases for convenience */}
      <Route path="/spending" element={<Dashboard />} />
    </Routes>
    </main>
    <MobileNav />
    </div>
  );
}
