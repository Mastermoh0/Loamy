import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';
const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos' }).format(new Date());

function PaymentLocation({ businessId, locationId }) {
  const base = `/businesses/${businessId}/locations/${locationId}/payments`;
  const [data, setData] = useState(null), [version, setVersion] = useState(0);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const [recordId, setRecordId] = useState(''), [invoiceId, setInvoiceId] = useState(''), [value, setValue] = useState('');
  const retry = useRef(null);
  useEffect(() => {
    let active = true;
    api(base).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [base, version]);
  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setNotice(message); setVersion((v) => v + 1); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  function submit(event, path, method, extra = {}, message = 'Saved.') {
    event.preventDefault(); const form = event.currentTarget; const values = { ...Object.fromEntries(new FormData(form)), ...extra };
    if ('account_id' in values && !values.account_id) values.account_id = null;
    action(async () => { await api(base + path, method, values); form.reset(); }, message);
  }
  return <>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    <button className="workspace-text-button" disabled={busy} onClick={() => { setError(''); setVersion((v) => v + 1); }}>Refresh payments</button>
    {!data ? <p role="status">Loading payment records…</p> : <>
      <h3>Invoice balances</h3><p>Balances use confirmed allocations. Income is recorded once in Financial records.</p>
      {!data.invoices.length && <p>Generate an invoice from an order to start matching payments.</p>}
      <ul className="workspace-order-list">{data.invoices.map((invoice) => <li key={invoice.id}><div><h4>{invoice.customer} · {invoice.status.replace('_', ' ')}</h4><p className="workspace-order-reference">{invoice.number}</p><p>Invoice {money(invoice.total)} · Allocated {money(invoice.allocated)} · Outstanding {money(invoice.outstanding)} · Overpayment {money(invoice.overpayment)}</p>
        <p>Receiving account: {data.accounts.find((account) => account.id === invoice.account_id)?.name || 'Not linked'}</p>
        {invoice.status !== 'cancelled' && <details><summary>Receiving account and allocation history</summary>
          <form onSubmit={(event) => submit(event, '/invoice-account', 'PUT', { invoice_id: invoice.id })}><fieldset disabled={busy}><label className="workspace-field"><span>Receiving account for {invoice.customer}</span><select name="account_id" required defaultValue={invoice.account_id || ''}><option value="">Choose account</option>{data.accounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.account_reference}</option>)}</select></label><button className="workspace-secondary">Save receiving account</button><p>Matching metadata only; the issued PDF is unchanged. Reverse active allocations before changing the account.</p></fieldset></form>
          {invoice.allocations.map((allocation) => <div key={allocation.id} className="workspace-operation-history"><p>{money(allocation.amount)} · {allocation.actor} · {allocation.reversed_at ? 'Reversed: ' + allocation.reversal_reason : 'Active'} · {allocation.note}</p>{!allocation.reversed_at && <form onSubmit={(event) => submit(event, `/allocations/${allocation.id}/reverse`, 'POST', {}, 'Allocation reversed. No money was refunded.')}><fieldset disabled={busy}><label className="workspace-field"><span>Reversal reason</span><input name="reason" required minLength={3} maxLength={240} /></label><button className="workspace-secondary">Reverse allocation</button></fieldset></form>}</div>)}
        </details>}
      </div></li>)}</ul>
      <details className="workspace-operation-block"><summary>Add receiving account</summary><form className="workspace-order-form" onSubmit={(event) => submit(event, '/accounts', 'POST')}><fieldset disabled={busy}>
        <label className="workspace-field"><span>Receiving account name</span><input name="name" required minLength={2} maxLength={100} /></label><label className="workspace-field"><span>Account reference</span><input name="account_reference" required minLength={2} maxLength={100} /></label><button className="workspace-primary">Save receiving account</button>
      </fieldset></form></details>
      <details className="workspace-operation-block"><summary>Record a cash payment or test bank credit</summary><p>Use existing income below when available. This creates one income entry. Test bank credits are entered evidence, not live or verified bank payments.</p>
        <form className="workspace-order-form" onSubmit={(event) => submit(event, '/credits', 'POST', {}, 'Payment recorded once. Review and allocate it below.')}><fieldset disabled={busy}>
          <label className="workspace-field"><span>Payment receiving account</span><select name="account_id"><option value="">Cash / no bank account</option>{data.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
          <label className="workspace-field"><span>Payment amount (NGN)</span><input name="amount" type="number" required min="0.01" step="0.01" /></label><label className="workspace-field"><span>Payment date</span><input name="occurred_on" type="date" required defaultValue={today()} max={today()} /></label>
          <label className="workspace-field"><span>Source reference / receipt number</span><input name="source_id" required minLength={3} maxLength={200} /><small>Use the original source reference for duplicate alerts, not another reference for the same money.</small></label>
          <label className="workspace-field"><span>Payer full name</span><input name="payer" required minLength={2} maxLength={120} /></label><label className="workspace-field"><span>Payment narration / invoice reference</span><textarea name="narration" required minLength={2} maxLength={1000} rows={3} /></label><button className="workspace-primary">Record payment evidence</button>
        </fieldset></form>
      </details>
      <h3>Review recorded credits</h3><p>Latest {data.credit_limit} posted income records. Suggestions never allocate automatically. Name/amount alone is not proof.</p>
      <ul className="workspace-order-list">{data.credits.map((credit) => <li key={credit.id}><div><h4>{credit.payer || credit.description} · {money(credit.amount)}</h4><p>Available {money(credit.available)} · {credit.occurred_on} · {credit.source}</p><p>{credit.source_id} {credit.narration}</p><p>{credit.candidates.length > 1 ? 'Ambiguous — several candidates' : credit.candidates.length ? 'Suggested match — confirmation required' : 'Unmatched — review evidence before selecting an invoice'}</p>
        {credit.candidates.map((candidate) => <button type="button" className="workspace-text-button" key={candidate.invoice_id} disabled={busy} onClick={() => { setRecordId(credit.id); setInvoiceId(candidate.invoice_id); setValue(String(Math.min(Number(credit.available), Number(data.invoices.find((invoice) => invoice.id === candidate.invoice_id).outstanding)))); }}>{data.invoices.find((invoice) => invoice.id === candidate.invoice_id).customer}: {candidate.reason}</button>)}
      </div></li>)}</ul>
      <form className="workspace-order-form" onSubmit={(event) => {
        event.preventDefault(); const values = { record_id: recordId, invoice_id: invoiceId, amount: value, note: new FormData(event.currentTarget).get('note') };
        const signature = JSON.stringify(values); if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
        action(async () => { await api(base + '/allocations', 'POST', { ...values, idempotency_key: retry.current.key }); retry.current = null; setValue(''); }, 'Payment allocated. Invoice balance updated without duplicate income.');
      }}><fieldset disabled={busy}><h3>Confirm payment allocation</h3>
        <label className="workspace-field"><span>Income record to allocate</span><select value={recordId} onChange={(event) => setRecordId(event.target.value)} required><option value="">Choose recorded income</option>{data.credits.filter((credit) => Number(credit.available) > 0).map((credit) => <option key={credit.id} value={credit.id}>{credit.payer || credit.description} · {money(credit.available)} available</option>)}</select></label>
        <label className="workspace-field"><span>Invoice receiving allocation</span><select value={invoiceId} onChange={(event) => setInvoiceId(event.target.value)} required><option value="">Choose invoice</option>{data.invoices.filter((invoice) => invoice.status !== 'cancelled').map((invoice) => <option key={invoice.id} value={invoice.id}>{invoice.customer} · {money(invoice.outstanding)} outstanding · {invoice.number}</option>)}</select></label>
        <p>Allocating more than the balance records an overpayment. It does not refund money.</p><label className="workspace-field"><span>Allocation amount (NGN)</span><input type="number" min="0.01" step="0.01" required value={value} onChange={(event) => setValue(event.target.value)} /></label><label className="workspace-field"><span>Evidence checked / allocation note</span><input name="note" required minLength={3} maxLength={240} /></label><button className="workspace-primary">Confirm allocation</button>
      </fieldset></form>
    </>}
  </>;
}

export default function WorkspacePayments({ businessId, locations }) {
  const [location, setLocation] = useState(locations[0]?.id || '');
  return <section><div className="workspace-section-heading"><div><h2>Payments & balances</h2><p>Review credits, confirm matches and see what is still owed.</p></div></div><label className="workspace-field workspace-order-location"><span>Payment location</span><select value={location} onChange={(event) => setLocation(event.target.value)}>{locations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><PaymentLocation key={location} businessId={businessId} locationId={location} /></section>;
}
