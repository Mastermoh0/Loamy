import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { workspaceRequest as api } from './services/workspaceService';

export default function WorkspaceVerification({ session, token, invitation, onVerified }) {
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const capture = session.mail_transport === 'capture';
  useEffect(() => {
    let active = true;
    if (capture) api('/email/inbox').then((data) => { if (active) setMessages(data.messages); })
      .catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [capture]);

  async function verify() {
    setBusy(true); setError('');
    try {
      await api('/email/verify', 'POST', { token });
      await onVerified();
      navigate(invitation ? `/business#invite=${encodeURIComponent(invitation)}` : '/business', { replace: true });
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }

  async function resend() {
    setBusy(true); setError(''); setNotice('');
    try {
      await api('/email/request', 'POST');
      if (capture) setMessages((await api('/email/inbox')).messages);
      setNotice(capture ? 'A new message is ready in your local inbox.' : 'Verification email sent. Check your inbox.');
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }

  return <section className="workspace-verification" aria-labelledby="verify-title">
    <h1 id="verify-title">Verify your email</h1>
    <p>Confirm <strong className="selectable">{session.user.email}</strong> before opening business records or accepting team access.</p>
    {capture ? <p className="workspace-local-note">Local inbox mode: no message is sent to a real mailbox. Completing this flow verifies your test account for this computer only.</p>
      : <p>Open the link in your verification email, then confirm below. Links expire after 30 minutes.</p>}
    {error && <p className="workspace-error" role="alert">{error}</p>}
    {!capture && session.last_verification_email?.status === 'failed' && <p className="workspace-error" role="alert">The verification email was not delivered. Check the local SMTP settings, then request another message.</p>}
    {notice && <p className="workspace-notice" role="status">{notice}</p>}
    {token && <div className="workspace-confirm-email"><h2>Confirm this verification link</h2>
      <p>Signed in as {session.user.email}. Only the matching account can use this link.</p>
      <button className="workspace-primary" disabled={busy} onClick={verify}>{busy ? 'Confirming…' : capture ? 'Verify test account' : 'Verify email address'}</button>
    </div>}
    {capture && <div className="workspace-local-inbox"><h2>Your local inbox</h2>
      {messages.length ? messages.map((mail, i) => <article key={mail.id}>
        <h3>{mail.subject}{i > 0 ? ' (older message)' : ''}</h3>
        <p>To: <span className="selectable">{mail.recipient}</span></p><p>This link works once and expires after 30 minutes.</p>
        <Link className="workspace-secondary" to={`${mail.verification_url.replace(window.location.origin, '')}${invitation ? `&invite=${encodeURIComponent(invitation)}` : ''}`}>Open verification link</Link>
      </article>) : <p>No verification message yet. Request one below.</p>}
    </div>}
    <button className="workspace-text-button" disabled={busy} onClick={resend}>{busy ? 'Please wait…' : 'Request a new verification email'}</button>
    <small>Wait one minute between requests. A new email replaces the previous link.</small>
  </section>;
}
