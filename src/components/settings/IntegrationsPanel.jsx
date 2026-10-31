import { Link } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faEnvelope, faBuildingColumns } from "@fortawesome/free-solid-svg-icons";
import { faWhatsapp } from "@fortawesome/free-brands-svg-icons";
import useSWR from "swr";
import {
  getSession, keys, fetchGmailStatus, fetchWhatsappStatus, fetchBankCount,
} from "../../services/settingsService";

function Row({ icon, title, detail, connected, loading, to, cta }) {
  return (
    <li className="settings-integration">
      <span className="settings-integration-icon"><FontAwesomeIcon icon={icon} /></span>
      <div className="settings-integration-text">
        <strong>{title}</strong>
        <span>{loading ? "Checking..." : detail}</span>
      </div>
      <span className={`settings-status${connected ? " on" : ""}`}>
        {loading ? "" : connected ? "Linked" : "Not linked"}
      </span>
      <Link to={to} className="settings-link-btn">{cta}</Link>
    </li>
  );
}

export default function IntegrationsPanel() {
  const { user_id: userId } = getSession();
  const gmail = useSWR(keys.gmail(userId), fetchGmailStatus);
  const whatsapp = useSWR(keys.whatsapp(userId), fetchWhatsappStatus);
  const banks = useSWR(keys.banks(userId), fetchBankCount);

  const bankCount = banks.data || 0;

  return (
    <ul className="settings-integrations">
      <Row
        icon={faEnvelope}
        title="Gmail"
        detail="Reads bank alerts and invoice emails"
        connected={gmail.data?.connected}
        loading={gmail.isLoading}
        to="/gmail-connect"
        cta={gmail.data?.connected ? "Manage" : "Connect"}
      />
      <Row
        icon={faWhatsapp}
        title="WhatsApp"
        detail={whatsapp.data?.phone || "Log spending by message"}
        connected={whatsapp.data?.linked}
        loading={whatsapp.isLoading}
        to="/dashboard"
        cta={whatsapp.data?.linked ? "Manage" : "Link"}
      />
      <Row
        icon={faBuildingColumns}
        title="Bank accounts"
        detail={bankCount ? `${bankCount} connected` : "No accounts yet"}
        connected={bankCount > 0}
        loading={banks.isLoading}
        to="/accounts"
        cta={bankCount ? "View" : "Add"}
      />
    </ul>
  );
}
