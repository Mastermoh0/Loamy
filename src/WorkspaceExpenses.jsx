import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';
const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos' }).format(new Date());

function ExpenseForm({ expense, busy, base, onSave, onClose }) {
  const [fileError, setFileError] = useState('');
  const [reading, setReading] = useState(false);
  const [extraction, setExtraction] = useState(null);
  const formRef = useRef(null);
  async function readFile(file) {
    if (!file?.size || file.size > 2 * 1024 * 1024) throw new Error('Choose a JPEG, PNG or PDF receipt no larger than 2 MB.');
    return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('The receipt could not be read. Choose the file again.')); reader.readAsDataURL(file); });
  }
  async function extract() {
    setReading(true); setFileError(''); setExtraction(null);
    try {
      const form = formRef.current;
      const receipt_base64 = await readFile(form.elements.receipt.files[0]);
      const result = await api(base + '/extract', 'POST', { receipt_base64 });
      for (const [field, value] of Object.entries(result.suggested)) {
        if (value && form.elements[field]) form.elements[field].value = value;
      }
      setExtraction(result);
    } catch (failure) { setFileError(failure.message); }
    finally { setReading(false); }
  }
  async function submit(event) {
    event.preventDefault(); const form = event.currentTarget; const values = Object.fromEntries(new FormData(form)); const file = values.receipt;
    if (!file?.size || file.size > 2 * 1024 * 1024) { setFileError('Choose a JPEG, PNG or PDF receipt no larger than 2 MB.'); return; }
    setReading(true); setFileError('');
    try {
      const receipt_base64 = await readFile(file);
      delete values.receipt; await onSave({ ...values, receipt_base64, extraction_id: extraction?.id || null });
    } catch (failure) { setFileError(failure.message); }
    finally { setReading(false); }
  }
  return <form ref={formRef} className="workspace-order-form" onSubmit={submit}><fieldset disabled={busy || reading}><h3>{expense ? 'Revise and resubmit expense' : 'Submit an expense'}</h3>
    <label className="workspace-field"><span>{expense ? 'Receipt for this revision (same file is allowed)' : 'Receipt evidence'}</span><input name="receipt" type="file" required accept="image/jpeg,image/png,application/pdf" onChange={() => { setExtraction(null); setFileError(''); }} /><small>JPEG, PNG or PDF, up to 2 MB. Extract up to three PDF pages, or fill the fields manually. Receipts stay private.</small></label>
    <button className="workspace-secondary" type="button" onClick={extract}>{reading ? 'Reading receipt…' : 'Extract receipt details'}</button>
    {extraction && <div className="workspace-receipt-extraction" role="status"><strong>Suggestions ready — review the fields below</strong><ul>{extraction.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul><p>Add the purchase purpose and category. Extraction does not submit, approve or post an expense.</p><details><summary>Read extracted text</summary><pre>{extraction.text || 'No readable text found.'}</pre></details></div>}
    <label className="workspace-field"><span>Expense vendor</span><input name="vendor" required minLength={2} maxLength={120} defaultValue={expense?.vendor || ''} /></label>
    <label className="workspace-field"><span>Expense purpose</span><textarea name="purpose" required minLength={3} maxLength={500} rows={3} defaultValue={expense?.purpose || ''} /></label>
    <label className="workspace-field"><span>Expense category</span><input name="category" required minLength={2} maxLength={60} defaultValue={expense?.category || ''} /></label>
    <div className="workspace-order-columns"><label className="workspace-field"><span>Expense amount (NGN)</span><input name="amount" type="number" required min="0.01" step="0.01" defaultValue={expense?.amount || ''} /></label><label className="workspace-field"><span>Expense date</span><input name="occurred_on" type="date" required max={today()} defaultValue={expense?.occurred_on || today()} /></label></div>
    {fileError && <p role="alert" className="workspace-error">{fileError}</p>}
    <div className="workspace-order-actions"><button className="workspace-primary">{reading || busy ? 'Please wait…' : expense ? 'Resubmit for review' : 'Submit for review'}</button><button className="workspace-text-button" type="button" onClick={onClose}>Close expense form</button></div>
  </fieldset></form>;
}

function ExpenseLocation({ businessId, locationId }) {
  const base = `/businesses/${businessId}/locations/${locationId}/expenses`;
  const [data, setData] = useState(null), [version, setVersion] = useState(0);
  const [editing, setEditing] = useState(null), [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [breakdown, setBreakdown] = useState(null);
  const retry = useRef(null);
  useEffect(() => {
    let active = true;
    api(base).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [base, version]);
  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setNotice(message); setVersion((v) => v + 1); setBreakdown(null); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  async function save(values) {
    const signature = JSON.stringify(values); if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    await action(async () => { await api(base + (editing ? `/${editing.id}` : ''), editing ? 'PUT' : 'POST', { ...values, idempotency_key: retry.current.key }); retry.current = null; setEditing(null); setCreating(false); }, 'Expense submitted for review. Nothing has been posted to the ledger.');
  }
  return <>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    <div className="workspace-order-actions"><button className="workspace-primary" disabled={busy || creating || !!editing} onClick={() => setCreating(true)}>Submit expense</button><button className="workspace-text-button" disabled={busy} onClick={() => { setError(''); setVersion((v) => v + 1); setBreakdown(null); }}>Refresh expenses</button></div>
    {(creating || editing) && <ExpenseForm key={editing?.id || 'new'} expense={editing} busy={busy} base={base} onSave={save} onClose={() => { setCreating(false); setEditing(null); retry.current = null; }} />}
    {!data ? <p role="status">Loading expenses…</p> : <>
      {data.can_review && <section><h3>Posted expense categories</h3><p>Totals cover all posted expense records at this location. Pending approvals are excluded; linked debits count once.</p><ul className="workspace-order-list">{data.categories.map((category) => <li key={category.category}><div><h4>{category.category}</h4><p>{category.count} posted records · {money(category.amount)}</p><button className="workspace-text-button" disabled={busy} onClick={async () => { setBusy(true); setError(''); try { const result = await api(base + '/categories/' + encodeURIComponent(category.category)); setBreakdown({ category: category.category, records: result.records }); } catch (failure) { setError(failure.message); } finally { setBusy(false); } }}>View {category.category} details</button></div></li>)}</ul>
        {breakdown && <section className="workspace-operation-block"><h4>{breakdown.category} details</h4><ul className="workspace-order-list">{breakdown.records.map((record) => <li key={record.id}><div><h4>{record.description} · {money(record.amount)}</h4><p>{record.occurred_on} · {record.source} · Recorded by {record.recorded_by} · Submitted by {record.submitter || 'No receipt submission linked'}</p>{record.expense_id && <a className="workspace-text-button" href={`/enterprise-api${base}/${record.expense_id}/receipt/${record.expense_revision}`} download>Download linked receipt</a>}</div></li>)}</ul></section>}
      </section>}
      <h3>{data.can_review ? 'Receipt submissions and review' : 'My receipt submissions'}</h3><p>Showing {data.expenses.length} of {data.count} submissions, latest first. A different person must review each submission.</p>
      <ul className="workspace-order-list">{data.expenses.map((expense) => <li key={expense.id}><div><h4>{expense.vendor} · {money(expense.amount)} · {expense.status.replace('_', ' ')}</h4><p>{expense.category} · {expense.occurred_on} · Submitted by {expense.submitter} · Version {expense.revision}</p><p>{expense.purpose}</p>
        {expense.ledger_status && <p>Ledger: {expense.ledger_status}{expense.ledger_void_reason ? ' — ' + expense.ledger_void_reason : ''}</p>}
        <div className="workspace-order-actions">{expense.versions.map((revision) => <a className="workspace-text-button" key={revision.revision} href={`/enterprise-api${base}/${expense.id}/receipt/${revision.revision}`} download>Receipt version {revision.revision}</a>)}</div>
        {expense.versions.filter((revision) => revision.extraction).map((revision) => <details key={revision.revision}><summary>Receipt suggestions for version {revision.revision}</summary><p>Suggested vendor: {revision.extraction.suggested.vendor || 'Not found'} · Suggested amount: {revision.extraction.suggested.amount ? money(revision.extraction.suggested.amount) : 'Not found'} · Suggested date: {revision.extraction.suggested.occurred_on || 'Not found'}</p><p>Submitted values are recorded in the history below. Suggestions are not proof of approval.</p><ul>{revision.extraction.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details>)}
        <details><summary>Submission and approval history</summary>{expense.versions.map((revision) => <p key={revision.revision}>Version {revision.revision} · {revision.vendor} · {money(revision.amount)} · {revision.category} · {revision.occurred_on}<br />{revision.purpose}</p>)}{expense.history.map((event, index) => <p key={index}>Version {event.revision} · {event.action} · {event.actor} · {new Date(event.created_at * 1000).toLocaleString('en-GB', { timeZone: 'Africa/Lagos' })}<br />{event.reason}</p>)}</details>
        {expense.submitter_id === data.actor_id && ['rejected', 'needs_clarification'].includes(expense.status) && <button className="workspace-secondary" disabled={busy || creating || !!editing} onClick={() => setEditing(expense)}>Revise {expense.vendor}</button>}
        {data.can_review && expense.status === 'submitted' && (expense.submitter_id === data.actor_id ? <p>Another owner, manager or finance member must review your submission.</p> : <form className="workspace-order-form" onSubmit={(event) => {
          event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); action(() => api(`${base}/${expense.id}/review`, 'POST', { ...values, revision: expense.revision }), 'Review recorded. Approval alone does not post money.');
        }}><fieldset disabled={busy}><label className="workspace-field"><span>Review decision for {expense.vendor}</span><select name="decision"><option value="approved">Approve</option><option value="needs_clarification">Request clarification</option><option value="rejected">Reject</option></select></label><label className="workspace-field"><span>Review reason</span><input name="reason" required minLength={3} maxLength={240} /></label><button className="workspace-secondary">Record review</button></fieldset></form>)}
        {data.can_review && expense.status === 'approved' && <form className="workspace-order-form" onSubmit={(event) => {
          event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); action(() => api(`${base}/${expense.id}/post`, 'POST', { record_id: values.record_id || null, reason: values.reason, confirm_new: values.confirm_new === 'on' }), 'Approved expense posted or linked once. Category totals updated.');
        }}><fieldset disabled={busy}><h4>Post approved expense</h4><label className="workspace-field"><span>Existing debit for {expense.vendor}</span><select name="record_id"><option value="">Create a new expense entry</option>{expense.debit_candidates?.map((record) => <option key={record.id} value={record.id}>{record.description} · matching amount/date/category</option>)}</select></label><p>Link an already recorded debit for the same purchase to avoid double-counting. The server checks location, amount, date and category.</p>
          <label className="workspace-order-check"><input name="confirm_new" type="checkbox" />I checked similar debits; this is a separate new expense.</label><label className="workspace-field"><span>Posting or linking reason</span><input name="reason" required minLength={3} maxLength={240} /></label><button className="workspace-primary">Post or link expense</button></fieldset></form>}
      </div></li>)}</ul>
    </>}
  </>;
}

export default function WorkspaceExpenses({ businessId, locations }) {
  const [location, setLocation] = useState(locations[0]?.id || '');
  return <section><div className="workspace-section-heading"><div><h2>Expenses & receipts</h2><p>Keep the receipt, submit it for review, then post or link the approved expense.</p></div></div><label className="workspace-field workspace-order-location"><span>Expense location</span><select value={location} onChange={(event) => setLocation(event.target.value)}>{locations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><ExpenseLocation key={location} businessId={businessId} locationId={location} /></section>;
}
