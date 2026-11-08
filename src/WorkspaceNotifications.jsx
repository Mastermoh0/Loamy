import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';
const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const statuses = { draft: 'Draft — not sent', captured: 'Captured locally — no email sent', accepted: 'Accepted by the email server — inbox arrival is unconfirmed', sending: 'Sending — please wait', failed: 'Not sent — check the recipient or service', unknown: 'Delivery uncertain — check before sending any new message' };

function NotificationLocation({ businessId, locationId }) {
  const base = `/businesses/${businessId}/locations/${locationId}/customer-notifications`;
  const [data, setData] = useState(null), [version, setVersion] = useState(0), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const retry = useRef(null);
  useEffect(() => { let active = true; api(base).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); }); return () => { active = false; }; }, [base, version]);
  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setNotice(message); setVersion((v) => v + 1); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  function prepare(event, invoice) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); const body = { ...values, invoice_id: invoice.id };
    const signature = JSON.stringify(body); if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    action(async () => { await api(base, 'POST', { ...body, idempotency_key: retry.current.key }); retry.current = null; }, 'Draft prepared below. Review the full message before confirming delivery.');
  }
  return <>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    <button className="workspace-secondary" disabled={busy} onClick={() => setVersion((v) => v + 1)}>Refresh customer messages</button>
    {!data ? <p role="status">Loading notification candidates…</p> : <>
      <p>{data.transport === 'capture' ? 'Local capture: no customer email will be sent.' : 'Messages use the configured email service after you explicitly confirm. Check the recipient and current payment evidence first.'} One notice per invoice in 24 hours; changed balances need a fresh draft.</p>
      <h3>Partial payments and overdue invoices</h3>{!data.candidates.length && <p>No eligible partial-payment or overdue balances at this location.</p>}
      <ul className="workspace-order-list">{data.candidates.map((invoice) => <li key={invoice.id}><div><h4>{invoice.customer} · {invoice.number}</h4><p>Allocated {money(invoice.payments.allocated)} · Remaining {money(invoice.payments.outstanding)} · Due {invoice.due_on || 'Not specified'}</p><form className="workspace-order-form" onSubmit={(event) => prepare(event, invoice)}><fieldset disabled={busy}>
        <label className="workspace-field"><span>Message type for {invoice.number}</span><select name="kind">{invoice.kinds.map((kind) => <option key={kind} value={kind}>{kind === 'partial_payment' ? 'Partial-payment update' : 'Overdue reminder'}</option>)}</select></label>
        <label className="workspace-field"><span>Customer email for {invoice.number}</span><input name="recipient" type="email" required maxLength={254} defaultValue={invoice.contact.includes('@') ? invoice.contact : ''} /></label><button className="workspace-secondary">Prepare message for review</button>
      </fieldset></form></div></li>)}</ul>
      <h3>Drafts and delivery history</h3><p>Showing the latest {data.history.length} drafts/attempts. Unknown delivery may already have reached the customer; it is never retried automatically.</p>
      <ul className="workspace-order-list">{data.history.map((item) => <li key={item.id}><div><h4>{item.subject}</h4><p>{item.recipient} · {statuses[item.status] || item.status}</p><details open={item.status === 'draft'}><summary>Review message text</summary><p className="workspace-order-prewrap">{item.body}</p></details>
        {['draft', 'failed'].includes(item.status) && <button className="workspace-primary" disabled={busy} onClick={() => action(async () => { const result = await api(`${base}/${item.id}/send`, 'POST', { confirm_retry: item.status === 'failed' }); setNotice(statuses[result.status]); }, data.transport === 'capture' ? 'Message captured locally. No customer email sent.' : 'Delivery attempt recorded. Check the status in history below.')}>{item.status === 'failed' ? 'Confirm retry of failed delivery' : data.transport === 'capture' ? 'Confirm local test delivery' : 'Confirm and send customer email'}</button>}
      </div></li>)}</ul>
    </>}
  </>;
}

export default function WorkspaceNotifications({ businessId, locations }) {
  const [location, setLocation] = useState(locations[0]?.id || '');
  return <section aria-labelledby="notifications-title"><div className="workspace-section-heading"><div><h2 id="notifications-title">Customer messages</h2><p>Review partial-payment updates and overdue reminders before delivery.</p></div></div><label className="workspace-field workspace-order-location"><span>Customer message location</span><select value={location} onChange={(e) => setLocation(e.target.value)}>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>{location && <NotificationLocation key={location} businessId={businessId} locationId={location} />}</section>;
}
