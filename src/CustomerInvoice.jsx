import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { workspaceRequest as api } from './services/workspaceService';
import { downloadWorkspace } from './services/workspaceDownloads';
import './BusinessWorkspace.css';
import { PricingBreakdown } from './WorkspacePricing';
const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);

export default function CustomerInvoice() {
  const { hash } = useLocation(); const token = new URLSearchParams(hash.slice(1)).get('token') || '';
  const [data, setData] = useState(null), [error, setError] = useState(''), [version, setVersion] = useState(0), [busy, setBusy] = useState(false);
  useEffect(() => { if (!token) return; let active = true; api('/customer-invoice', 'POST', { token }).then((result) => { if (active) { setData(result); setError(''); } }).catch((failure) => { if (active) { setData(null); setError(failure.status === 422 ? 'This invoice link is incomplete or invalid. Ask the business for a fresh link.' : failure.message); } }); return () => { active = false; }; }, [token, version]);
  async function download() { setBusy(true); setError(''); try { await downloadWorkspace('/customer-invoice/pdf', { token }, 'customer-invoice.pdf'); } catch (failure) { setError(failure.message); } finally { setBusy(false); } }
  const invoice = token ? data?.snapshot : null;
  const displayError = token ? error : 'This invoice link is incomplete. Ask the business for a fresh link.';
  return <div className="business-workspace"><section className="workspace-content"><h1>Customer invoice</h1><p>Private invoice link. Please keep it with the intended recipient.</p>{displayError && <p role="alert" className="workspace-error">{displayError}</p>}{token && !data && !displayError && <p role="status">Opening invoice…</p>}
    {invoice && <article className="workspace-invoice-paper"><h2>{invoice.profile.invoice_name}</h2><p>{invoice.location_name} · {invoice.profile.address}</p><p>{invoice.number} · Issued {invoice.issued_on} · Due {invoice.due_on || 'Not specified'}</p><h3>Bill to: {invoice.customer_name}</h3><p>{invoice.customer_contact}</p><ul className="workspace-order-list">{invoice.lines.map((line, index) => <li key={index}><div><h4>{line.name}</h4><p>{line.description} · {line.quantity} × {money(line.unit_price)}</p></div><strong>{money(line.total)}</strong></li>)}</ul><PricingBreakdown pricing={invoice.pricing} /><p>Total {money(invoice.total)}</p><p className="workspace-notice">{data.payments.status.replace('_', ' ')} · Confirmed allocations {money(data.payments.allocated)} · Remaining {money(data.payments.outstanding)} · Excess {money(data.payments.overpayment)}</p><p>The original PDF is an issued invoice, not a payment receipt. If a recent payment is missing, contact the business before paying again.</p>{invoice.local_preview && <p>Local preview with fictional test data.</p>}<p className="workspace-order-prewrap">{invoice.profile.payment_instructions}</p><p>Payment reference: {invoice.order_reference}</p><div className="workspace-order-actions"><button className="workspace-primary" disabled={busy} onClick={download}>Download issued invoice PDF</button><button className="workspace-secondary" disabled={busy} onClick={() => { setError(''); setVersion((v) => v + 1); }}>Refresh current balance</button></div></article>}
  </section></div>;
}
