import { useState } from 'react';

const currency = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);

export function PricingBreakdown({ pricing }) {
  if (!pricing) return null;
  return <div className="workspace-pricing-breakdown"><p>Subtotal <strong>{currency(pricing.subtotal)}</strong></p><p>Discount <strong>−{currency(pricing.discount)}</strong></p>{pricing.discount_reason && <p>{pricing.discount_reason}</p>}<p>{pricing.tax_label} ({pricing.tax_rate}%) <strong>{currency(pricing.tax)}</strong></p></div>;
}

export default function WorkspacePricing({ pricing, busy, onSave }) {
  const [editing, setEditing] = useState(false);
  return <section className="workspace-order-profile"><div className="workspace-section-heading"><div><h3>Taxes for new orders</h3><p>{pricing.tax_label}: {pricing.tax_rate}%. Tax is added after any discount. Existing orders keep their saved breakdown.</p></div><button className="workspace-text-button" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? 'Close tax settings' : 'Edit tax settings'}</button></div>
    {editing && <form onSubmit={async (event) => { event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); if (await onSave(values)) setEditing(false); }}><fieldset disabled={busy}>
      <label className="workspace-field"><span>Tax name</span><input name="tax_label" required minLength={2} maxLength={60} defaultValue={pricing.tax_label} /></label>
      <label className="workspace-field"><span>Tax rate (%)</span><input name="tax_rate" type="number" required min="0" max="100" step="0.01" defaultValue={pricing.tax_rate} /></label>
      <p>Enter the rate approved for this location. Zero disables tax for new orders. Service prices exclude tax; this setting does not file or remit tax.</p>
      <button type="submit" className="workspace-primary">Save tax settings</button>
    </fieldset></form>}
  </section>;
}
