import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';
import WorkspaceInvoice from './WorkspaceInvoice';
import WorkspacePricing, { PricingBreakdown } from './WorkspacePricing';
import WorkspaceBalanceAlerts from './WorkspaceBalanceAlerts';

const currency = (amount) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(amount);
const minor = (amount) => Math.round(Number(amount) * 100);
const rateAmount = (amount, basisPoints) => Number.isSafeInteger(amount) && Number.isSafeInteger(basisPoints) ? Number((BigInt(amount) * BigInt(basisPoints) + 5000n) / 10000n) : 0;

function ServiceForm({ service, busy, onSave, onClose }) {
  return <form className="workspace-order-form" onSubmit={(event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    onSave({ name: values.name, description: values.description, price: values.price, active: values.active === 'on' });
  }}><fieldset disabled={busy}>
    <h3>{service.id ? 'Edit service' : 'Add service'}</h3>
    <label className="workspace-field"><span>Service name</span><input name="name" required minLength={2} maxLength={120} defaultValue={service.name} /></label>
    <label className="workspace-field"><span>Description (optional)</span><input name="description" maxLength={500} defaultValue={service.description} /></label>
    <label className="workspace-field"><span>Unit price (NGN)</span><input name="price" type="number" required min="0.01" step="0.01" max="99999999.99" defaultValue={service.price} /></label>
    <label className="workspace-order-check"><input name="active" type="checkbox" defaultChecked={service.active !== false} />Available for new orders</label>
    <div className="workspace-order-actions"><button className="workspace-primary" type="submit">{busy ? 'Saving…' : 'Save service'}</button><button type="button" className="workspace-text-button" onClick={onClose}>Cancel</button></div>
  </fieldset></form>;
}

function NewOrder({ services, pricing, canDiscount, busy, onSave, onClose }) {
  const [lines, setLines] = useState([{ service_id: '', quantity: '1' }]);
  const [discountType, setDiscountType] = useState('none');
  const [discountValue, setDiscountValue] = useState('');
  const available = services.filter((service) => service.active);
  const subtotal = lines.reduce((sum, line) => sum + minor(available.find((s) => s.id === line.service_id)?.price || 0) * Number(line.quantity || 0), 0);
  const discount = discountType === 'percent' ? rateAmount(subtotal, minor(discountValue || 0)) : discountType === 'fixed' ? minor(discountValue || 0) : 0;
  const tax = rateAmount(Math.max(0, subtotal - discount), minor(pricing.tax_rate));
  const total = subtotal - discount + tax;
  function update(index, key, value) { setLines((current) => current.map((line, i) => i === index ? { ...line, [key]: value } : line)); }
  return <form className="workspace-order-form" onSubmit={(event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    onSave({ customer_name: values.customer_name, customer_contact: values.customer_contact, customer_email: values.customer_email, customer_whatsapp: values.customer_whatsapp,
      additional_emails: [values.extra_email_1,values.extra_email_2,values.extra_email_3].filter(Boolean), preferred_channel: values.preferred_channel, whatsapp_consent: values.whatsapp_consent==='on', expected_tax_rate: pricing.tax_rate,
      discount_type: discountType, discount_value: discountType === 'none' ? '0' : discountValue, discount_reason: values.discount_reason || '',
      lines: lines.map((line) => ({ service_id: line.service_id, quantity: Number(line.quantity), expected_price: available.find((s) => s.id === line.service_id)?.price })) });
  }}><fieldset disabled={busy}>
    <h3>New order</h3>
    <div className="workspace-order-columns">
      <label className="workspace-field"><span>Customer full name</span><input name="customer_name" required minLength={2} maxLength={120} autoComplete="off" /></label>
      <label className="workspace-field"><span>Other customer contact (optional)</span><input name="customer_contact" minLength={3} maxLength={254} autoComplete="off" /><small>Use a separate email or WhatsApp field below for delivery. Saving sends no message.</small></label>
    </div>
    <div className="workspace-order-columns"><label className="workspace-field"><span>Primary customer email (optional)</span><input type="email" name="customer_email" maxLength={254}/></label><label className="workspace-field"><span>Customer WhatsApp number (optional)</span><input name="customer_whatsapp" placeholder="+2348012345678" pattern="\+[1-9][0-9]{7,14}" maxLength={16}/><small>Include + and the country code.</small></label></div>
    <details><summary>Additional customer emails (optional)</summary>{[1,2,3].map(n=><label className="workspace-field" key={n}><span>Additional email {n}</span><input type="email" name={`extra_email_${n}`} maxLength={254}/></label>)}</details>
    <label className="workspace-field"><span>Preferred delivery channel</span><select name="preferred_channel" defaultValue="none"><option value="none">No preference recorded</option><option value="email">Email</option><option value="whatsapp">WhatsApp</option></select></label><label className="workspace-order-check"><input type="checkbox" name="whatsapp_consent"/>Customer agreed to WhatsApp invoices and payment follow-ups.</label><p>Enter at least one customer contact. Contact choices are saved with this order.</p>
    {lines.map((line, index) => <div className="workspace-order-line" key={index}>
      <label className="workspace-field"><span>Service {index + 1}</span><select required value={line.service_id} onChange={(event) => update(index, 'service_id', event.target.value)}>
        <option value="">Choose a service</option>{available.filter((service) => service.id === line.service_id || !lines.some((other) => other.service_id === service.id)).map((service) => <option key={service.id} value={service.id}>{service.name} · {currency(service.price)}</option>)}
      </select></label>
      <label className="workspace-field"><span>Quantity {index + 1}</span><input type="number" required min="1" max="10000" step="1" value={line.quantity} onChange={(event) => update(index, 'quantity', event.target.value)} /></label>
      {lines.length > 1 && <button type="button" className="workspace-text-button" aria-label={`Remove line ${index + 1}`} onClick={() => setLines((current) => current.filter((_, i) => i !== index))}>Remove</button>}
    </div>)}
    {lines.length < Math.min(20, available.length) && <button type="button" className="workspace-text-button" onClick={() => setLines((current) => [...current, { service_id: '', quantity: '1' }])}>Add another item</button>}
    {canDiscount && <><label className="workspace-field"><span>Order discount</span><select value={discountType} onChange={(event) => { setDiscountType(event.target.value); setDiscountValue(''); }}><option value="none">No discount</option><option value="fixed">Fixed amount (NGN)</option><option value="percent">Percentage (%)</option></select></label>{discountType !== 'none' && <div className="workspace-order-columns"><label className="workspace-field"><span>{discountType === 'fixed' ? 'Discount amount (NGN)' : 'Discount percentage (%)'}</span><input type="number" required min="0.01" max={discountType === 'percent' ? '100' : '99999999.99'} step="0.01" value={discountValue} onChange={(event) => setDiscountValue(event.target.value)} /></label><label className="workspace-field"><span>Discount reason (shown on invoice)</span><input name="discount_reason" required minLength={3} maxLength={240} /></label></div>}</>}
    <PricingBreakdown pricing={{ subtotal: subtotal / 100, discount: discount / 100, tax: tax / 100, tax_label: pricing.tax_label, tax_rate: pricing.tax_rate }} />
    {discount >= subtotal && subtotal > 0 && <p role="alert" className="workspace-error">Reduce the discount to leave a positive order amount.</p>}
    <p className="workspace-order-total">Order total <strong>{currency(Math.max(0, total) / 100)}</strong></p>
    <small>Prices are checked when saving. An open order is not a payment or an invoice.</small>
    <div className="workspace-order-actions"><button type="submit" disabled={discount >= subtotal} className="workspace-primary">{busy ? 'Saving…' : 'Save order'}</button><button type="button" className="workspace-text-button" onClick={onClose}>Discard draft</button></div>
  </fieldset></form>;
}

export default function WorkspaceOrders({ businessId, role, locations, initialLocation = '' }) {
  const [locationId, setLocationId] = useState(initialLocation || locations[0]?.id || '');
  const [view, setView] = useState('orders');
  const [period, setPeriod] = useState('today');
  const [data, setData] = useState(null);
  const [orders, setOrders] = useState(null);
  const [detail, setDetail] = useState(null);
  const [editing, setEditing] = useState(null);
  const [newOrder, setNewOrder] = useState(false);
  const [profileForm, setProfileForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [version, setVersion] = useState(0);
  const retry = useRef(null);
  const canEdit = ['owner', 'manager'].includes(role);
  const canOrder = ['owner', 'manager', 'front_desk'].includes(role);
  const base = `/businesses/${businessId}/locations/${locationId}`;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api(`${base}/catalogue`), api(`${base}/orders?period=${period}`)])
      .then(([catalogue, saved]) => { if (!cancelled) { setData(catalogue); setOrders(saved); } })
      .catch((failure) => { if (!cancelled) { setError(failure.message); setData(null); setOrders(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [base, period, version]);

  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setNotice(message); setLoading(true); setVersion((value) => value + 1); return true; }
    catch (failure) { setError(failure.message); return false; }
    finally { setBusy(false); }
  }

  function changeLocation(value) {
    setLocationId(value); setLoading(true); setError(''); setData(null); setOrders(null); setDetail(null); setEditing(null); setNewOrder(false); setProfileForm(false); setNotice(''); retry.current = null;
  }

  async function saveOrder(values) {
    const signature = JSON.stringify(values);
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    await action(async () => {
      const saved = await api(`${base}/orders`, 'POST', { ...values, idempotency_key: retry.current.key });
      // Close the draft once saved even if the follow-up detail request fails.
      retry.current = null; setNewOrder(false); setDetail(null); setLoading(true); setVersion((value) => value + 1);
      setDetail(await api(`${base}/orders/${saved.id}`));
    }, 'Order saved. No payment has been recorded.');
  }

  return <section aria-labelledby="workspace-orders-title">
    <div className="workspace-section-heading"><div><h2 id="workspace-orders-title">Services & orders</h2><p>Choose a location, build an order and keep the agreed prices on record.</p></div></div>
    <label className="workspace-field workspace-order-location"><span>Order location</span><select value={locationId} disabled={busy || newOrder || !!editing || profileForm} onChange={(event) => changeLocation(event.target.value)}>{locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}</select></label>
    <div className="workspace-order-actions"><button className={view === 'orders' ? 'workspace-secondary' : 'workspace-text-button'} aria-pressed={view === 'orders'} disabled={busy || newOrder || !!editing || profileForm} onClick={() => setView('orders')}>Orders</button><button className={view === 'catalogue' ? 'workspace-secondary' : 'workspace-text-button'} aria-pressed={view === 'catalogue'} disabled={busy || newOrder || !!editing || profileForm} onClick={() => setView('catalogue')}>Service catalogue</button></div>
    {error && <p role="alert" className="workspace-error">{error} <button className="workspace-text-button" disabled={busy} onClick={() => { setLoading(true); setError(''); setVersion((v) => v + 1); }}>Refresh catalogue and orders</button></p>}
    {notice && <p role="status" className="workspace-notice">{notice}</p>}
    <WorkspaceBalanceAlerts base={base} onOpen={id=>action(async()=>setDetail(await api(`${base}/orders/${id}`)),'')}/>
    {loading && <p role="status">Loading services and orders…</p>}
    {data && orders && <>
      {view === 'catalogue' ? <>
        {canEdit && <WorkspacePricing pricing={data.pricing} busy={busy} onSave={(values) => action(() => api(`${base}/pricing`, 'PUT', values), 'Tax settings saved for new orders.')} />}
        <div className="workspace-section-heading"><div><h3>Location catalogue</h3><p>Prices in NGN. Unavailable services remain on past orders.</p></div>{canEdit && <button className="workspace-secondary" disabled={busy || !!editing} onClick={() => setEditing({ active: true })}>Add service</button>}</div>
        {editing && <ServiceForm key={editing.id || 'new'} service={editing} busy={busy} onClose={() => setEditing(null)} onSave={(values) => action(async () => {
          await api(`${base}/services${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PUT' : 'POST', values); setEditing(null);
        }, 'Service saved. Past orders keep their original prices.')} />}
        <ul className="workspace-order-list">{data.services.map((service) => <li key={service.id}><div><h4>{service.name}</h4><p>{service.description || 'No description'}</p><small>{service.active ? 'Available' : 'Unavailable for new orders'}</small></div><strong>{currency(service.price)}</strong>{canEdit && <button className="workspace-text-button" disabled={busy || !!editing} onClick={() => setEditing(service)}>Edit {service.name}</button>}</li>)}</ul>
        {!data.services.length && <p>No services yet. {canEdit ? 'Add your first service to start taking orders.' : 'Ask your owner or manager to add services for this location.'}</p>}
        <section className="workspace-order-profile"><div className="workspace-section-heading"><div><h3>Business details for orders</h3><p>Saved with each order for future invoices.</p></div>{canEdit && <button className="workspace-text-button" disabled={busy} onClick={() => setProfileForm(!profileForm)}>{profileForm ? 'Close details form' : 'Edit business details'}</button>}</div>
          {profileForm ? <form className="workspace-order-form" onSubmit={(event) => { event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); action(async () => { await api(`${base}/profile`, 'PUT', values); setProfileForm(false); }, 'Business details saved.'); }}><fieldset disabled={busy}>
            <label className="workspace-field"><span>Invoice business name</span><input name="invoice_name" required minLength={2} maxLength={100} defaultValue={data.profile.invoice_name} /></label>
            <label className="workspace-field"><span>Invoice address</span><input name="address" required minLength={2} maxLength={240} defaultValue={data.profile.address} /></label>
            <label className="workspace-field"><span>Payment instructions (optional)</span><textarea name="payment_instructions" rows={3} maxLength={1000} defaultValue={data.profile.payment_instructions} /></label>
            <button className="workspace-primary" type="submit">Save business details</button>
          </fieldset></form> : <><strong>{data.profile.invoice_name}</strong><p>{data.profile.address}</p><p className="workspace-order-prewrap">{data.profile.payment_instructions || 'No payment instructions added.'}</p></>}
        </section>
      </> : <>
        <div className="workspace-section-heading"><div><h3>Location orders</h3><p>Today uses the Lagos calendar date ({orders.today}). Counts include every order in this view.</p></div>{canOrder && <button className="workspace-primary" disabled={busy || newOrder || !data.services.some((s) => s.active)} onClick={() => { setNewOrder(true); setDetail(null); setNotice(''); }}>New order</button>}</div>
        {!data.services.some((service) => service.active) && <p>No active services. Open the service catalogue {canEdit ? 'to add or activate a service.' : 'and ask your manager to add one.'}</p>}
        {newOrder && <NewOrder services={data.services} pricing={data.pricing} canDiscount={canEdit} busy={busy} onSave={saveOrder} onClose={() => { setNewOrder(false); retry.current = null; }} />}
        <label className="workspace-field workspace-order-location"><span>Order period</span><select value={period} disabled={busy || newOrder || loading} onChange={(event) => { setPeriod(event.target.value); setLoading(true); setDetail(null); }}><option value="today">Today</option><option value="all">All dates</option></select></label>
        <p className="workspace-order-counts">{orders.counts.total} total · {orders.counts.open} open · {orders.counts.cancelled} cancelled</p>
        <p>Showing {orders.orders.length} of {orders.counts.total} orders, latest first. Open means saved, not paid.</p>
        <ul className="workspace-order-list">{orders.orders.map((order) => <li key={order.id}><div><h4>{order.customer_name}</h4><p className="workspace-order-reference">{order.reference}</p><small>{order.order_date} · {order.status === 'open' ? 'Open' : 'Cancelled'}</small></div><strong>{currency(order.total)}</strong><button className="workspace-text-button" disabled={busy} aria-label={`Open order for ${order.customer_name}`} onClick={() => action(async () => setDetail(await api(`${base}/orders/${order.id}`)), '')}>View order</button></li>)}</ul>
        {!orders.orders.length && <p>No orders {period === 'today' ? 'today' : 'saved'} for this location.</p>}
        {detail && <section className="workspace-order-detail" aria-labelledby="order-detail-title"><div className="workspace-section-heading"><h3 id="order-detail-title">Order details</h3><button className="workspace-text-button" disabled={busy} onClick={() => setDetail(null)}>Close order</button></div>
          <p className="workspace-order-reference">{detail.reference}</p><p><strong>{detail.customer_name}</strong><br />{detail.customer_contact}</p><p>{detail.status === 'open' ? 'Open' : 'Cancelled'} · Created by {detail.created_by} · {detail.order_date}</p>
          <ul className="workspace-order-list">{detail.lines.map((line, index) => <li key={index}><div><h4>{line.name}</h4><p>{line.description}</p><small>{line.quantity} × {currency(line.unit_price)}</small></div><strong>{currency(line.total)}</strong></li>)}</ul>
          <PricingBreakdown pricing={detail.pricing} />
          <p className="workspace-order-total">Total <strong>{currency(detail.total)}</strong></p>
          <p><strong>{detail.profile.invoice_name}</strong><br />{detail.profile.address}</p><p className="workspace-order-prewrap">{detail.profile.payment_instructions}</p>
          <WorkspaceInvoice key={`${detail.id}-${detail.status}`} base={base} order={detail} canIssue={canOrder} canSchedule={['owner','manager','finance'].includes(role)} parentBusy={busy} />
          {detail.status === 'cancelled' ? <p>Cancelled by {detail.cancelled_by_name} on {new Date(detail.cancelled_at * 1000).toLocaleString('en-GB', { timeZone: 'Africa/Lagos' })}: {detail.cancel_reason}</p> : canOrder && <form onSubmit={(event) => {
            event.preventDefault(); const reason = new FormData(event.currentTarget).get('reason');
            action(async () => { await api(`${base}/orders/${detail.id}/cancel`, 'POST', { reason }); setDetail(await api(`${base}/orders/${detail.id}`)); }, 'Order cancelled. The original items and prices remain on record.');
          }}><fieldset disabled={busy}><label className="workspace-field"><span>Reason for cancellation</span><input name="reason" required minLength={3} maxLength={240} /></label><button className="workspace-secondary" type="submit">Cancel this order</button><p>Cancellation also cancels its invoice. It keeps the original records and does not issue a refund, change the financial ledger or notify the customer automatically.</p></fieldset></form>}
        </section>}
      </>}
    </>}
  </section>;
}
