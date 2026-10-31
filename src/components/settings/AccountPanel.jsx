import { getSession } from "../../services/settingsService";

export default function AccountPanel() {
  const session = getSession();
  const name = session.name || "Loamy user";

  return (
    <>
      <div className="settings-profile">
        <div className="settings-avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</div>
        <div>
          <h3>{name}</h3>
          <p>{session.email || "No email on file"}</p>
        </div>
        <span className="settings-badge">Pro</span>
      </div>
      <dl className="settings-fields">
        <div><dt>Name</dt><dd>{name}</dd></div>
        <div><dt>Email</dt><dd>{session.email || "Not set"}</dd></div>
        <div><dt>Plan</dt><dd>Loamy AI Pro</dd></div>
      </dl>
      <p className="settings-note">Editing your name or email is not available yet.</p>
    </>
  );
}
