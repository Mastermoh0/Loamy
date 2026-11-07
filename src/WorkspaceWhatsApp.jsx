import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';

export default function WorkspaceWhatsApp({ businessId, locationId, onSelect, disabled, refresh }) {
  const base = `/businesses/${businessId}/locations/${locationId}/whatsapp`;
  const [data, setData] = useState(null), [version, setVersion] = useState(0);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [code, setCode] = useState(null);
  const retry = useRef(null);
  useEffect(() => {
    let active = true;
    api(base).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [base, version, refresh]);
  async function action(work, message = '') {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setVersion((v) => v + 1); setNotice(message); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  async function simulate(event) {
    event.preventDefault(); const form = event.currentTarget; const file = form.elements.receipt.files[0];
    await action(async () => {
      if (!file?.size || file.size > 2 * 1024 * 1024) throw new Error('Choose a JPEG, PNG or PDF receipt up to 2 MB.');
      const receipt_base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('The receipt could not be read.')); reader.readAsDataURL(file); });
      const caption = form.elements.caption.value;
      const signature = JSON.stringify([receipt_base64, caption]);
      if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      await api(base + '/preview-message', 'POST', { receipt_base64, caption, idempotency_key: retry.current.key });
      retry.current = null; form.reset();
    }, 'Simulated WhatsApp receipt received. Open the draft below; nothing is approved or posted.');
  }
  return <details className="workspace-operation-block"><summary>WhatsApp receipt inbox</summary><p>Link your own WhatsApp sender, send a receipt privately to the configured business number, then open and confirm your draft here. Group capture is not enabled.</p>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    {!data ? <p role="status">Loading your receipt inbox…</p> : <>
      {!data.live_configured && <p>Live WhatsApp is not connected. Samuel must configure the approved business number, provider credentials and receipt worker.</p>}
      {data.phone_ids.map((pid) => <div key={pid}><p>Configured business phone ID: {pid}. Ask your operator for its corresponding WhatsApp number.</p><button type="button" className="workspace-secondary" disabled={busy || disabled} onClick={() => action(async () => setCode(await api(base + '/link-code', 'POST', { phone_id: pid })))}>Create sender-link code</button></div>)}
      {code && <label className="workspace-field"><span>Send this exact message privately to the configured business number within 10 minutes</span><input readOnly value={code.message} onFocus={(e) => e.target.select()} /><small>Only the sender that delivers this one-use code will be linked to your account and this location. Keep it private.</small></label>}
      {data.links.map((link) => <p key={link.id}>Sender ending {link.sender.slice(-4)} · {link.revoked_at ? 'revoked' : 'linked'} {!link.revoked_at && <button className="workspace-text-button" disabled={busy || disabled} onClick={() => action(() => api(`${base}/links/${link.id}/revoke`, 'POST', { reason: 'Staff disconnected their WhatsApp sender' }), 'Sender disconnected.')}>Disconnect sender</button>}</p>)}
      <button className="workspace-text-button" disabled={busy} onClick={() => setVersion((v) => v + 1)}>Refresh receipt inbox</button>
      {data.local_preview && <details><summary>Simulate an incoming receipt locally</summary><form className="workspace-order-form" onSubmit={simulate}><fieldset disabled={busy || disabled}><p>This exercises the draft flow on this computer. It sends no WhatsApp message and does not verify a real sender.</p><label className="workspace-field"><span>Simulated WhatsApp receipt</span><input type="file" name="receipt" required accept="image/jpeg,image/png,application/pdf" /></label><label className="workspace-field"><span>Simulated receipt caption</span><input name="caption" maxLength={500} /></label><button className="workspace-secondary">Add simulated receipt to inbox</button></fieldset></form></details>}
      {!data.messages.length && <p>No receipt messages yet for your account at this location.</p>}
      <ul className="workspace-order-list">{data.messages.map((message) => <li key={message.id}><div><h4>{message.simulated ? 'Simulated receipt' : 'WhatsApp receipt'} · {message.status}</h4><p>{message.caption || 'No caption'} · {new Date(message.received_at * 1000).toLocaleString('en-GB', { timeZone: 'Africa/Lagos' })}</p>{message.error && <p>{message.error}</p>}
        {message.status === 'ready' && <button className="workspace-secondary" disabled={busy || disabled} onClick={() => action(async () => onSelect(await api(`${base}/messages/${message.id}/draft`)))}>Open receipt draft</button>}
        {message.status === 'failed' && <button className="workspace-text-button" disabled={busy || disabled} onClick={() => action(() => api(`${base}/messages/${message.id}/retry`, 'POST'), 'Receipt queued for another retrieval attempt.')}>Retry receipt retrieval</button>}
        {['ready', 'failed', 'queued'].includes(message.status) && <button className="workspace-text-button" disabled={busy || disabled} onClick={() => action(() => api(`${base}/messages/${message.id}/discard`, 'POST', { reason: 'Staff dismissed an unsubmitted receipt message' }), 'Receipt dismissed with evidence retained.')}>Dismiss receipt message</button>}
      </div></li>)}</ul>
    </>}
  </details>;
}
