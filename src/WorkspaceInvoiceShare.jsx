import { useEffect, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';

export default function WorkspaceInvoiceShare({ base, invoice, disabled }) {
  const endpoint = `${base}/invoices/${invoice.id}/shares`;
  const [data, setData] = useState(null), [version, setVersion] = useState(0), [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  useEffect(() => { let active = true; api(endpoint).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); }); return () => { active = false; }; }, [endpoint, version]);
  async function action(work) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setVersion((v) => v + 1); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <section className="workspace-operation-block"><h4>Share a customer invoice link</h4><p>Anyone holding this link can view this invoice, its customer details and current balance. Share privately with the intended customer. Links expire and can be revoked; files already downloaded cannot be recalled.</p>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    {invoice.status === 'issued' && <form onSubmit={(event) => { event.preventDefault(); const days = Number(new FormData(event.currentTarget).get('expires_days')); action(async () => setLink(await api(endpoint, 'POST', { expires_days: days }))); }}><fieldset disabled={disabled || busy}><label className="workspace-field workspace-order-location"><span>Customer link expires after</span><select name="expires_days"><option value="1">1 day</option><option value="7">7 days</option><option value="30">30 days</option></select></label><button className="workspace-secondary">Create private customer link</button></fieldset></form>}
    {link && <><label className="workspace-field"><span>New customer invoice link — copy now</span><input readOnly value={link.url} onFocus={(e) => e.target.select()} /><small>Shown only in this session. Creating the link sends no customer message.</small></label><div className="workspace-order-actions"><a className="workspace-text-button" href={link.url} target="_blank" rel="noreferrer">Preview customer invoice</a><button className="workspace-text-button" disabled={busy} onClick={() => action(async () => { if (navigator.share) { await navigator.share({ title: 'Invoice ' + invoice.number, url: link.url }); setNotice('Share action handed to your device. Delivery is not confirmed.'); } else { await navigator.clipboard.writeText(link.url); setNotice('Link copied. Paste it into your chosen private customer channel.'); } })}>Share or copy customer link</button></div></>}
    {data && <details><summary>Manage existing customer links</summary>{!data.shares.length && <p>No links created for this invoice.</p>}{data.shares.map((s) => <p key={s.id}>Created {new Date(s.created_at * 1000).toLocaleString('en-GB')} · {s.revoked_at ? 'Revoked' : s.expired ? 'Expired' : 'Active'} · Expires {new Date(s.expires_at * 1000).toLocaleString('en-GB')} {!s.revoked_at && <button className="workspace-text-button" disabled={busy || disabled} onClick={() => action(async () => { await api(`${endpoint}/${s.id}/revoke`, 'POST'); if (link?.id === s.id) setLink(null); setNotice('Customer link revoked.'); })}>Revoke invoice link</button>}</p>)}</details>}
  </section>;
}
