import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';
import WorkspaceInvoiceShare from './WorkspaceInvoiceShare';
import { PricingBreakdown } from './WorkspacePricing';
import WorkspaceCommunications from './WorkspaceCommunications';

const amount = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const DELIVERY = {
  captured: 'Captured locally — no email was sent',
  sending: 'Sending — wait before trying another copy',
  accepted: 'Accepted by the email server — inbox delivery is not confirmed',
  failed: 'Not sent — check the recipient or email configuration',
  unknown: 'Delivery uncertain — it may have been sent. Check before sending another copy',
};

export default function WorkspaceInvoice({ base, order, canIssue, canSchedule, parentBusy }) {
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [recipient, setRecipient] = useState(order.customer_contact.includes('@') ? order.customer_contact : '');
  const [completed, setCompleted] = useState(false);
  const [version, setVersion] = useState(0);
  const retry = useRef(null);
  const endpoint = `${base}/orders/${order.id}/invoice`;
  const disabled = busy || parentBusy;
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos' }).format(new Date());

  useEffect(() => {
    let cancelled = false;
    api(endpoint).then((result) => { if (!cancelled) setInvoice(result.invoice); })
      .catch((failure) => { if (!cancelled) setError(failure.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [endpoint, version]);

  async function generate(event) {
    event.preventDefault();
    const due = new FormData(event.currentTarget).get('due_on');
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api(endpoint, 'POST', { due_on: due || null });
      setInvoice(result.invoice); setNotice('Invoice generated. No email has been sent.');
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }

  async function send(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    const email = recipient.trim();
    if (retry.current?.recipient !== email) retry.current = { recipient: email, key: crypto.randomUUID() };
    try {
      const result = await api(`${endpoint}/email`, 'POST', { recipient: email, idempotency_key: retry.current.key });
      setCompleted(true); setNotice(DELIVERY[result.status]); setVersion((value) => value + 1);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }

  const snapshot = invoice?.snapshot;
  return <section className="workspace-invoice" aria-labelledby="workspace-invoice-title">
    <div className="workspace-section-heading"><div><h3 id="workspace-invoice-title">Invoice</h3><p>Generate once from this order’s saved details. Balances use confirmed payment allocations.</p></div></div>
    {error && <p className="workspace-error" role="alert">{error} <button className="workspace-text-button" disabled={disabled} onClick={() => { setError(''); setLoading(true); setVersion((value) => value + 1); }}>Refresh invoice</button></p>}
    {notice && <p className="workspace-notice" role="status">{notice}</p>}
    {loading ? <p role="status">Loading invoice…</p> : !invoice ? order.status === 'cancelled' ? <p>Cancelled orders cannot be invoiced.</p> : canIssue ? <form onSubmit={generate}><fieldset disabled={disabled}>
      <label className="workspace-field workspace-order-location"><span>Payment due date (optional)</span><input type="date" name="due_on" min={today} /></label>
      <p>Check the customer, items and business details above. The issued invoice and due date will be fixed.</p>
      <button className="workspace-primary" type="submit">{busy ? 'Generating…' : 'Generate invoice'}</button>
    </fieldset></form> : <p>No invoice yet. An owner, manager or front-desk member can generate it.</p> : <>
      <p className="workspace-notice">{invoice.payment_status.replace('_', ' ')} · Allocated {amount(invoice.payments.allocated)} · Outstanding {amount(invoice.payments.outstanding)} · Overpayment {amount(invoice.payments.overpayment)}</p>
      <div className="workspace-order-actions"><a className="workspace-secondary" href={`/enterprise-api${endpoint}/pdf`} download>Download invoice PDF</a><button className="workspace-text-button" disabled={disabled} onClick={() => { setLoading(true); setVersion((value) => value + 1); }}>Refresh balances and delivery</button></div>
      <article className="workspace-invoice-paper" aria-label="Invoice preview">
        <div className="workspace-section-heading"><h4>{invoice.status === 'cancelled' ? 'Cancelled invoice' : 'Invoice'}</h4><span>Version {invoice.version}</span></div>
        <p className="workspace-order-reference">{invoice.number}</p>
        <h4>{snapshot.profile.invoice_name}</h4><p>{snapshot.location_name}<br />{snapshot.profile.address}</p>
        <p>Issued: {snapshot.issued_on} · Due: {snapshot.due_on || 'Not specified'}</p>
        <p><strong>Bill to: {snapshot.customer_name}</strong><br />{snapshot.customer_contact}</p>
        <p className="workspace-order-reference">Order reference: {snapshot.order_reference}</p>
        <ul className="workspace-order-list">{snapshot.lines.map((line, index) => <li key={index}><div><h4>{line.name}</h4><p>{line.description}</p><small>{line.quantity} × {amount(line.unit_price)}</small></div><strong>{amount(line.total)}</strong></li>)}</ul>
        <PricingBreakdown pricing={snapshot.pricing} />
        <p className="workspace-order-total">Invoice total <strong>{amount(snapshot.total)}</strong></p>
        <p>{invoice.status === 'cancelled' ? 'Cancelled — do not pay this invoice.' : 'Original issued invoice — not a receipt. Current payment balance is shown above.'}</p>
        {snapshot.profile.payment_instructions && <><h4>Payment instructions</h4><p className="workspace-order-prewrap">{snapshot.profile.payment_instructions}</p><p>Include the order reference above.</p></>}
      </article>
      <WorkspaceCommunications base={base} invoice={invoice} canSend={canIssue&&!parentBusy} canSchedule={canSchedule&&!parentBusy}/>
      {canIssue && invoice.status === 'issued' && <form className="workspace-invoice-email" onSubmit={send}><fieldset disabled={disabled}>
        <h4>Email this invoice</h4>
        <p>{invoice.mail_transport === 'capture' ? 'Local test inbox: the message and PDF attachment stay on this computer. No customer email is sent.' : 'Sends the invoice PDF through the configured email service. Check the customer address before sending.'}</p>
        <label className="workspace-field"><span>Customer email for invoice</span><input type="email" required maxLength={254} value={recipient} disabled={completed} onChange={(event) => setRecipient(event.target.value)} /></label>
        <button className="workspace-primary" disabled={completed} type="submit">{busy ? 'Processing…' : invoice.mail_transport === 'capture' ? 'Test invoice email' : 'Send invoice email'}</button>
        {completed && <><p>Sending another copy is a separate action. If delivery is uncertain, check with the recipient first. Copies are limited to one per minute.</p><button type="button" className="workspace-text-button" onClick={() => { retry.current = null; setCompleted(false); setNotice('Another copy is ready to send. Review the recipient before submitting.'); }}>Prepare another copy</button></>}
      </fieldset></form>}
      <section className="workspace-invoice-history" aria-label="Invoice email history"><h4>Email history</h4>
        {!invoice.deliveries.length && <p>No email requested for this invoice.</p>}
        <ul className="workspace-order-list">{invoice.deliveries.map((delivery) => <li key={delivery.id}><div><h4>{delivery.recipient}</h4><p>{DELIVERY[delivery.status]}</p><small>{new Date(delivery.created_at * 1000).toLocaleString('en-GB', { timeZone: 'Africa/Lagos' })}</small>
          {delivery.transport === 'capture' && <details><summary>View captured email</summary><p>{delivery.subject}</p><p className="workspace-order-prewrap">{delivery.body}</p><a className="workspace-text-button" href={`/enterprise-api${endpoint}/email/${delivery.id}/attachment`} download>Download captured PDF attachment</a>{invoice.status === 'cancelled' && <p>This historical attachment was issued before cancellation. Use the marked-cancelled invoice above for the current status.</p>}</details>}
        </div></li>)}</ul>
      </section>
      {canIssue && <WorkspaceInvoiceShare base={base} invoice={invoice} disabled={disabled} />}
    </>}
  </section>;
}
