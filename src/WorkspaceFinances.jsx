import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';

const formatMoney = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

export default function WorkspaceFinances({ businessId, role, locations, initialLocation, onChanged }) {
  const [location, setLocation] = useState(initialLocation || (role === 'owner' ? '' : locations[0]?.id || ''));
  const [data, setData] = useState(null);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [voiding, setVoiding] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  // Keep the same reference on uncertain network failure; edits create a new reference.
  const saveRef = useRef({ values: '', key: '' });
  useEffect(() => {
    let active = true;
    const query = location ? `?location_id=${encodeURIComponent(location)}` : '';
    api(`/businesses/${businessId}/financial-records${query}`).then((result) => { if (active) { setData(result); setError(''); } })
      .catch((failure) => { if (active) { setData(null); setError(failure.message); } });
    return () => { active = false; };
  }, [businessId, location, version]);

  async function save(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const signature = JSON.stringify(values);
    if (saveRef.current.values !== signature) saveRef.current = { values: signature, key: crypto.randomUUID() };
    setBusy(true); setError(''); setNotice('');
    try {
      await api(`/businesses/${businessId}/financial-records`, 'POST', { ...values, currency: 'NGN', idempotency_key: saveRef.current.key });
      saveRef.current = { values: '', key: '' };
      setAdding(false); setData(null); setVersion((v) => v + 1); setNotice('Financial record saved.'); onChanged();
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }

  async function voidRecord(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true); setError(''); setNotice('');
    try {
      await api(`/businesses/${businessId}/financial-records/${voiding}/void`, 'POST', values);
      setVoiding(''); setData(null); setVersion((v) => v + 1); setNotice('Record voided. Its history is retained and totals have been updated.'); onChanged();
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }

  return <section aria-labelledby="finances-title">
    <div className="workspace-section-heading"><div><h2 id="finances-title">Financial records</h2><p>Recorded income and expenses, kept with the location they belong to.</p></div>
      <button className="workspace-secondary" disabled={busy} onClick={() => setAdding(!adding)}>{adding ? 'Close form' : 'Add financial record'}</button></div>
    {error && <p className="workspace-error" role="alert">{error}</p>}
    {notice && <p className="workspace-notice" role="status">{notice}</p>}
    <label className="workspace-field workspace-finance-filter"><span>Show records for</span><select value={location} disabled={busy} onChange={(e) => { setLocation(e.target.value); setData(null); setVoiding(''); }}>
      {role === 'owner' && <option value="">All locations</option>}{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
    </select></label>
    {data ? <><dl className="workspace-finance-totals"><div><dt>Recorded income</dt><dd>{formatMoney(data.totals.income)}</dd></div>
      <div><dt>Recorded expenses</dt><dd>{formatMoney(data.totals.expenses)}</dd></div><div><dt>Net cash flow</dt><dd>{formatMoney(data.totals.net)}</dd></div></dl>
      <p className="workspace-local-note">Totals cover all posted records in this view. Net cash flow is income minus expenses, not a bank balance. Gmail imports are not connected to this local ledger.</p></> : !error && <p role="status">Loading financial records…</p>}
    {adding && <form className="workspace-record-form" onSubmit={save}><fieldset disabled={busy}>
      <legend>Record a financial movement</legend>
      <div className="workspace-record-fields">
        <label className="workspace-field"><span>Location</span><select name="location_id" defaultValue={location || locations[0]?.id} required>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label className="workspace-field"><span>Type</span><select name="direction"><option value="income">Income</option><option value="expense">Expense</option></select></label>
        <label className="workspace-field"><span>Amount (NGN)</span><input name="amount" type="number" inputMode="decimal" min="0.01" max="999999999999.99" step="0.01" required /></label>
        <label className="workspace-field"><span>Transaction date</span><input name="occurred_on" type="date" defaultValue={today()} max={today()} required /></label>
        <label className="workspace-field"><span>Description</span><input name="description" minLength={2} maxLength={240} placeholder="e.g. Room booking payment" required /></label>
        <label className="workspace-field"><span>Category</span><input name="category" minLength={2} maxLength={60} placeholder="e.g. Accommodation" required /></label>
      </div><button type="submit" className="workspace-primary">{busy ? 'Saving…' : 'Save financial record'}</button>
    </fieldset></form>}
    {data && <><p className="workspace-record-count">{data.count ? `Showing ${data.records.length} of ${data.count} records · latest first` : 'No records yet for this location.'}</p>
      <ul className="workspace-record-list">{data.records.map((record) => <li key={record.id} className={record.status === 'voided' ? 'workspace-record-voided' : ''}>
        <div className="workspace-record-description"><h3>{record.description}</h3><p>{record.location_name} · {record.category} · {record.occurred_on}</p>
          <small>Recorded by {record.recorded_by} · Manual entry{record.status === 'voided' ? ` · Voided: ${record.void_reason}` : ''}</small></div>
        <strong className="workspace-record-amount">{record.direction === 'expense' ? '−' : '+'}{formatMoney(record.amount)}</strong>
        {record.status === 'posted' ? <button className="workspace-text-button" disabled={busy} aria-label={`Void ${record.description}`} onClick={() => setVoiding(voiding === record.id ? '' : record.id)}>Void</button> : <span className="workspace-record-status">Voided</span>}
        {voiding === record.id && <form className="workspace-void-form" onSubmit={voidRecord}><label className="workspace-field"><span>Reason for voiding</span><input name="reason" minLength={3} maxLength={240} required /></label>
          <p>The original entry stays in the history and will be excluded from totals.</p><button className="workspace-secondary" disabled={busy} type="submit">Confirm void</button><button className="workspace-text-button" disabled={busy} type="button" onClick={() => setVoiding('')}>Cancel</button></form>}
      </li>)}</ul></>}
  </section>;
}
