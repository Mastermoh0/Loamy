import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';

const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos' }).format(new Date());
async function readInvoice(file) {
  if (!file?.size || file.size > 2 * 1024 * 1024) throw new Error('Choose a JPEG, PNG or PDF invoice up to 2 MB.');
  return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('The invoice could not be read.')); reader.readAsDataURL(file); });
}

function SupplierLocation({ businessId, locationId }) {
  const base = `/businesses/${businessId}/locations/${locationId}/supplier-bills`;
  const [data, setData] = useState(null), [version, setVersion] = useState(0);
  const [creating, setCreating] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [extraction, setExtraction] = useState(null);
  const [emailSource,setEmailSource]=useState(null),[attachmentIndex,setAttachmentIndex]=useState(0);
  const formRef = useRef(null), retry = useRef(null), paymentRetry = useRef(null);
  useEffect(() => {
    let active = true;
    api(base).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [base, version]);
  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setVersion((v) => v + 1); setNotice(message); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  async function extract() {
    await action(async () => {
      const form = formRef.current;
      const receipt_base64 = emailSource?emailSource.preview.attachments.find(a=>a.index===attachmentIndex).receipt_base64:await readInvoice(form.elements.invoice.files[0]);
      const result = await api(`/businesses/${businessId}/locations/${locationId}/expenses/extract`, 'POST', { receipt_base64 });
      for (const [key, value] of Object.entries(result.suggested)) {
        const field = key === 'occurred_on' ? 'issued_on' : key;
        if (value && form.elements[field]) form.elements[field].value = value;
      }
      setExtraction(result);
    }, 'Suggestions filled. Confirm the invoice number, total, dates and purpose.');
  }
  async function importBill(event) {
    event.preventDefault(); const form = event.currentTarget;
    await action(async () => {
      const values = Object.fromEntries(new FormData(form)); const receipt_base64 = emailSource?'':await readInvoice(values.invoice); delete values.invoice;
      const body = { ...values, receipt_base64, extraction_id: extraction?.id || null, ...(emailSource?{source_email_base64:emailSource.base64,email_attachment_index:attachmentIndex}:{}) };
      const signature = JSON.stringify(body);
      if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      await api(base, 'POST', { ...body, idempotency_key: retry.current.key });
      retry.current = null; setCreating(false); setExtraction(null);setEmailSource(null);
    }, 'Supplier bill imported. No paid expense was created.');
  }
  async function allocate(event, bill) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    const signature = JSON.stringify([bill.id, values]);
    if (paymentRetry.current?.signature !== signature) paymentRetry.current = { signature, key: crypto.randomUUID() };
    await action(async () => { await api(`${base}/${bill.id}/payments`, 'POST', { ...values, idempotency_key: paymentRetry.current.key }); paymentRetry.current = null; }, 'Existing debit linked. Cash flow still counts the original expense once.');
  }
  function reasoned(path, message) {
    const reason = window.prompt('Explain this correction (at least 3 characters):');
    if (reason) action(() => api(path, 'POST', { reason }), message);
  }
  return <>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    <div className="workspace-order-actions"><button className="workspace-primary" disabled={busy} onClick={() => { setCreating(!creating); setExtraction(null); }}>{creating ? 'Close import form' : 'Import supplier invoice'}</button><button className="workspace-text-button" disabled={busy} onClick={() => setVersion((v) => v + 1)}>Refresh supplier bills</button></div>
    {creating && <form ref={formRef} className="workspace-order-form" onSubmit={importBill}><fieldset disabled={busy}><h3>Import a bill owed</h3>
      <details><summary>Import an attachment from an email file</summary><p>Export the supplier email as .eml and choose it here (up to 2 MB, 1–5 PDF/JPEG/PNG attachments). This reviews one email file; it does not connect or poll your mailbox. Sender headers are unverified.</p><label className="workspace-field"><span>Supplier email (.eml)</span><input type="file" accept=".eml,message/rfc822" disabled={busy} onChange={e=>{const file=e.target.files[0];setEmailSource(null);setExtraction(null);if(file)action(async()=>{const base64=await readInvoice(file);const preview=await api(base+'/email-preview','POST',{email_base64:base64});setEmailSource({base64,preview});setAttachmentIndex(preview.attachments[0].index);},'Email attachments ready for review. Nothing has been posted.');}}/></label>{emailSource&&<><p>Unverified sender: {emailSource.preview.sender}<br/>Subject: {emailSource.preview.subject}</p><label className="workspace-field"><span>Email invoice attachment</span><select value={attachmentIndex} onChange={e=>{setAttachmentIndex(Number(e.target.value));setExtraction(null);}}>{emailSource.preview.attachments.map(a=><option key={a.index} value={a.index}>{a.filename}</option>)}</select></label><button className="workspace-text-button" type="button" onClick={()=>{setEmailSource(null);setExtraction(null);}}>Use an invoice file instead</button></>}</details>
      {!emailSource&&<label className="workspace-field"><span>Supplier invoice file</span><input name="invoice" type="file" required accept="image/png,image/jpeg,application/pdf" onChange={() => setExtraction(null)} /><small>Private original evidence, up to 2 MB. Importing records a liability, not payment.</small></label>}
      <button type="button" className="workspace-secondary" onClick={extract}>Extract invoice details</button>
      {extraction && <div className="workspace-receipt-extraction"><ul>{extraction.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
      <label className="workspace-field"><span>Supplier name</span><input name="vendor" required minLength={2} maxLength={120} /></label>
      <label className="workspace-field"><span>Supplier invoice number</span><input name="reference" required maxLength={100} /><small>Confirm the supplier’s original reference to prevent duplicate imports.</small></label>
      <label className="workspace-field"><span>Bill description</span><input name="description" required minLength={3} maxLength={240} /></label>
      <label className="workspace-field"><span>Bill category</span><input name="category" required minLength={2} maxLength={60} /></label>
      <label className="workspace-field"><span>Invoice total (NGN)</span><input name="amount" type="number" required min="0.01" step="0.01" /></label>
      <div className="workspace-order-columns"><label className="workspace-field"><span>Invoice date</span><input name="issued_on" type="date" required max={today()} defaultValue={today()} /></label><label className="workspace-field"><span>Payment due date</span><input name="due_on" type="date" required defaultValue={today()} /></label></div>
      <button className="workspace-primary" type="submit">{busy ? 'Please wait…' : 'Save unpaid bill'}</button>
    </fieldset></form>}
    {!data ? <p role="status">Loading supplier bills…</p> : <>
      <div className="workspace-operation-block"><h3>Money owed to suppliers</h3><p><strong>{money(data.outstanding)}</strong> outstanding · {money(data.overdue)} overdue</p><p>Separate from money received and paid expenses. To record a payment, create or confirm its existing expense debit in Financial records, then link it below.</p></div>
      <p>Showing {data.bills.length} of {data.count} bills. Imported details and original files stay in history; correct errors by voiding and importing a new invoice.</p>
      {!data.bills.length && <p>No supplier bills yet at this location.</p>}
      <ul className="workspace-order-list">{data.bills.map((bill) => <li key={bill.id}><div><h4>{bill.vendor} · {bill.reference}</h4><p>{bill.description} · {bill.category}</p><p>Total {money(bill.amount)} · Paid {money(bill.paid)} · Owed {money(bill.outstanding)} · {bill.payment_status.replace('_', ' ')}{bill.overdue ? ' · Overdue' : ''}</p><p>Invoice {bill.issued_on} · Due {bill.due_on}</p>{bill.email_source&&<details><summary>Email import provenance</summary><p>Unverified sender: {bill.email_source.sender}<br/>Subject: {bill.email_source.subject}</p><p className="workspace-order-reference">Email SHA-256: {bill.email_source.email_sha256}<br/>Attachment SHA-256: {bill.email_source.attachment_sha256}</p><p>Headers are not proof of sender identity. The original selected invoice is retained; no mailbox was connected.</p></details>}
        <a className="workspace-text-button" href={`/enterprise-api${base}/${bill.id}/invoice`} download>Download original supplier invoice</a>
        {bill.void_reason && <p>Voided: {bill.void_reason}</p>}
        {bill.suggestions && <details><summary>Original extraction suggestions</summary><p>{bill.suggestions.vendor || 'Vendor not found'} · {bill.suggestions.amount ? money(bill.suggestions.amount) : 'Amount not found'} · {bill.suggestions.occurred_on || 'Date not found'}</p></details>}
        {bill.status === 'open' && bill.payment_status !== 'paid' && <form className="workspace-order-form" onSubmit={(event) => allocate(event, bill)}><fieldset disabled={busy}><h4>Link a recorded payment</h4><label className="workspace-field"><span>Existing expense debit for {bill.reference}</span><select name="record_id" required><option value="">Choose a recorded expense</option>{data.debits.map((debit) => <option key={debit.id} value={debit.id}>{debit.description} · {debit.occurred_on} · {money(debit.available)} available</option>)}</select></label><label className="workspace-field"><span>Amount to link to {bill.reference} (NGN)</span><input name="amount" type="number" required min="0.01" step="0.01" /></label><label className="workspace-field"><span>Payment check for {bill.reference}</span><input name="reason" required minLength={3} maxLength={240} placeholder="Confirm supplier, evidence and amount" /></label><button className="workspace-secondary">Link payment to bill</button></fieldset></form>}
        {!!bill.payments.length && <details><summary>Payment and correction history</summary>{bill.payments.map((payment) => <div className="workspace-operation-history" key={payment.id}><p>{money(payment.amount)} · {payment.reason}{payment.reversed_at ? ` · Reversed: ${payment.reverse_reason}` : ''}</p>{!payment.reversed_at && <button className="workspace-text-button" disabled={busy} onClick={() => reasoned(`${base}/${bill.id}/payments/${payment.id}/reverse`, 'Payment allocation reversed; original debit retained.')}>Reverse this bill allocation</button>}</div>)}</details>}
        {bill.status === 'open' && <button className="workspace-text-button" disabled={busy} onClick={() => reasoned(`${base}/${bill.id}/void`, 'Supplier bill voided with history retained.')}>Void supplier bill {bill.reference}</button>}
      </div></li>)}</ul>
    </>}
  </>;
}

export default function WorkspaceSuppliers({ businessId, locations }) {
  const [location, setLocation] = useState(locations[0]?.id || '');
  return <section aria-labelledby="suppliers-title"><div className="workspace-section-heading"><div><h2 id="suppliers-title">Supplier bills</h2><p>Import invoices, track what is owed and match payments to recorded expenses.</p></div></div><label className="workspace-field workspace-order-location"><span>Supplier bill location</span><select value={location} onChange={(e) => setLocation(e.target.value)}>{locations.map((l) => <option value={l.id} key={l.id}>{l.name}</option>)}</select></label>{location && <SupplierLocation key={location} businessId={businessId} locationId={location} />}</section>;
}
