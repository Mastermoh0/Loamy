import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faChevronLeft, faChevronRight } from "@fortawesome/free-solid-svg-icons";
import useSWR from "swr";
import Sidebar from "./components/Sidebar";
import AccountPanel from "./components/settings/AccountPanel";
import InfoPanel from "./components/settings/InfoPanel";
import FinancialPanel from "./components/settings/FinancialPanel";
import IntegrationsPanel from "./components/settings/IntegrationsPanel";
import DataPanel from "./components/settings/DataPanel";
import {
  getSession, logoutUser, keys, fetchGmailStatus, fetchWhatsappStatus, fetchBankCount,
} from "./services/settingsService";
import "./InvoicesPage.css";
import "./SettingsPage.css";

const SECTIONS = [
  { id: "account", label: "Account", description: "Your profile and plan" },
  { id: "notifications", label: "Notifications", description: "Reminders and alerts" },
  { id: "security", label: "Security", description: "Sign-in and session" },
  { id: "business", label: "Business preferences", description: "How Loamy treats business spending" },
  { id: "financial", label: "Financial preferences", description: "Currency and categories" },
  { id: "integrations", label: "Integrations", description: "Gmail, WhatsApp and banks" },
  { id: "data", label: "Data management", description: "What Loamy remembers about you" },
];

function renderPanel(id) {
  switch (id) {
    case "account":
      return <AccountPanel />;
    case "notifications":
      return (
        <InfoPanel
          rows={[
            ["Invoice reminders", "Daily at 5 PM, in the app"],
            ["Review queue nudges", "Shown as they come in"],
          ]}
          note="Turning individual notifications on or off is not available yet."
        />
      );
    case "security":
      return (
        <InfoPanel
          rows={[
            ["Sign-in", "Email and password, or Google"],
            ["Session", "Stays signed in on this browser until you log out"],
          ]}
          note="Password changes are not available yet. Logging out clears everything Loamy cached on this browser."
        />
      );
    case "business":
      return (
        <InfoPanel
          rows={[["Business and personal", "Loamy separates them from what you tell it in chat and in the review queue"]]}
          note="There are no saved business preferences to edit yet."
        />
      );
    case "financial":
      return <FinancialPanel />;
    case "integrations":
      return <IntegrationsPanel />;
    case "data":
      return <DataPanel />;
    default:
      return null;
  }
}

function useIntegrationSummary(userId) {
  const gmail = useSWR(keys.gmail(userId), fetchGmailStatus);
  const whatsapp = useSWR(keys.whatsapp(userId), fetchWhatsappStatus);
  const banks = useSWR(keys.banks(userId), fetchBankCount);
  const anyLinked = gmail.data?.connected || whatsapp.data?.linked || (banks.data || 0) > 0;
  return anyLinked ? "Linked" : "";
}

export default function SettingsPage() {
  const navigate = useNavigate();
  const session = getSession();
  const [activeId, setActiveId] = useState("account");
  const [showDetailOnMobile, setShowDetailOnMobile] = useState(false);
  const [confirmingLogout, setConfirmingLogout] = useState(false);
  const integrationValue = useIntegrationSummary(session.user_id);

  const rowValue = { account: "Pro", integrations: integrationValue };
  const active = SECTIONS.find((s) => s.id === activeId);

  const selectSection = (id) => {
    setActiveId(id);
    setShowDetailOnMobile(true);
  };

  const confirmLogout = async () => {
    await logoutUser(session.user_id);
    navigate("/");
  };

  return (
    <div className="invoices-page settings-page">
      <Sidebar />

      <main className="invoices-main settings-main">
        <header className="settings-header">
          <h1>Settings</h1>
          <p>Manage your account, connections and what Loamy remembers.</p>
        </header>

        <div className="settings-layout" data-view={showDetailOnMobile ? "detail" : "list"}>
          <nav className="settings-list" aria-label="Settings sections">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`settings-row${s.id === activeId ? " active" : ""}`}
                aria-current={s.id === activeId ? "page" : undefined}
                onClick={() => selectSection(s.id)}
              >
                <span>{s.label}</span>
                <span className="settings-row-end">
                  {rowValue[s.id] && (
                    <span className={s.id === "account" ? "settings-row-pro" : "settings-row-value"}>
                      {rowValue[s.id]}
                    </span>
                  )}
                  <FontAwesomeIcon icon={faChevronRight} />
                </span>
              </button>
            ))}
            <button type="button" className="settings-logout" onClick={() => setConfirmingLogout(true)}>
              Logout
            </button>
          </nav>

          <section className="settings-detail" aria-labelledby="settings-detail-title">
            <button type="button" className="settings-back" onClick={() => setShowDetailOnMobile(false)}>
              <FontAwesomeIcon icon={faChevronLeft} /> Settings
            </button>
            <h2 id="settings-detail-title">{active.label}</h2>
            <p className="settings-detail-sub">{active.description}</p>
            {renderPanel(activeId)}
          </section>
        </div>
      </main>

      {confirmingLogout && (
        <div className="settings-modal-overlay" role="presentation" onClick={() => setConfirmingLogout(false)}>
          <div
            className="settings-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="logout-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="logout-title">Log out of Loamy?</h3>
            <p>This clears your session and any synced email data stored on this browser.</p>
            <div className="settings-modal-actions">
              <button type="button" className="settings-btn-ghost" onClick={() => setConfirmingLogout(false)}>
                Cancel
              </button>
              <button type="button" className="settings-btn-danger" onClick={confirmLogout}>
                Log out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
