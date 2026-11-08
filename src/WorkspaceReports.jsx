import { useEffect, useRef, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';
import { downloadWorkspace } from './services/workspaceDownloads';
const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos' }).format(new Date());

export default function WorkspaceReports({ businessId, locations, owner }) {
  const [location, setLocation] = useState(owner ? '' : locations[0]?.id || '');
  const [data, setData] = useState(null), [scenario, setScenario] = useState({ days: 90, available_cash: null, confirm_complete_history: false }), [version, setVersion] = useState(0);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const retry = useRef(null);
  useEffect(() => {
    if (!owner) return;
    let active = true;
    api(`/businesses/${businessId}/financial-insights`, 'POST', { ...scenario, location_id: location || null }).then((result) => { if (active) setData(result); }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [businessId, owner, location, scenario, version]);
  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); setNotice(message); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  function estimate(event) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); setData(null); setError('');
    setScenario({ days: Number(values.days), available_cash: values.cash || null, confirm_complete_history: values.complete === 'on' });
  }
  function addCommitment(event) {
    event.preventDefault(); const form = event.currentTarget; const values = Object.fromEntries(new FormData(form));
    const signature = JSON.stringify(values); if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    action(async () => { await api(`/businesses/${businessId}/recurring-commitments`, 'POST', { ...values, idempotency_key: retry.current.key }); retry.current = null; form.reset(); setVersion((v) => v + 1); }, 'Recurring commitment recorded. No expense or payment was created.');
  }
  return <section aria-labelledby="reports-title"><div className="workspace-section-heading"><div><h2 id="reports-title">Insights & reports</h2><p>Understand recorded activity and download its supporting history.</p></div></div>
    <label className="workspace-field workspace-order-location"><span>Report location</span><select value={location} onChange={(e) => { setData(null); setLocation(e.target.value); }}>{owner && <option value="">All locations</option>}{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
    {error && <p className="workspace-error" role="alert">{error}</p>}{notice && <p className="workspace-notice" role="status">{notice}</p>}
    <section className="workspace-operation-block"><h3>Download financial history</h3><p>A ZIP report with spreadsheet-ready CSVs, a totals/coverage manifest and optional original invoices/linked receipts. Current invoice balances are clearly separated from cash movements in the selected dates.</p>
      <form className="workspace-order-form" onSubmit={(event) => { event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); action(() => downloadWorkspace(`/businesses/${businessId}/financial-history/export`, { start: values.start, end: values.end, location_id: location || null, include_evidence: values.evidence === 'on' }, 'loamy-financial-history.zip'), 'Report downloaded with its coverage notes.'); }}><fieldset disabled={busy}>
        <div className="workspace-order-columns"><label className="workspace-field"><span>Report from</span><input type="date" name="start" required max={today()} defaultValue={today()} /></label><label className="workspace-field"><span>Report through</span><input type="date" name="end" required max={today()} defaultValue={today()} /></label></div><label className="workspace-order-check"><input name="evidence" type="checkbox" defaultChecked />Include original invoices and linked receipt files</label><p>Up to 366 days, 5,000 ledger records and 25 MB of original files. Narrow the dates/location if the report is too large. Unposted receipts and unrelated private messages are excluded.</p><button className="workspace-primary">{busy ? 'Preparing…' : 'Download financial report'}</button>
      </fieldset></form>
    </section>
    {owner && <>
      <section className="workspace-operation-block"><h3>Recorded cash burn & runway</h3><form className="workspace-order-form" onSubmit={estimate}><fieldset disabled={busy}>
        <label className="workspace-field"><span>Completed days to observe</span><select name="days" defaultValue="90"><option value="30">30 days</option><option value="90">90 days</option><option value="180">180 days</option></select></label><label className="workspace-field"><span>Available cash to model (NGN, optional)</span><input name="cash" type="number" min="0" step="0.01" /><small>Enter a verified amount yourself. Loamy has no live bank balance; this scenario is not saved as a transaction.</small></label><label className="workspace-order-check"><input type="checkbox" name="complete" />I confirmed the selected locations’ recorded activity covers this period.</label><button className="workspace-secondary">Calculate recorded estimate</button>
      </fieldset></form>
      {!data ? (!error && <p role="status">Loading recorded insights…</p>) : <><p>{data.period.start} to {data.period.end} · {data.record_count} posted records · In {money(data.inflow)} · Out {money(data.outflow)}</p><p>Recorded net burn: {money(data.net_burn)} over {data.period.days} completed days · Average {money(data.daily_net_burn)} per day.</p><p><strong>{data.runway_days === null ? 'Runway unavailable' : `Estimated runway: ${data.runway_days} days`}</strong> · {data.runway_reason}</p><details><summary>Assumptions and coverage</summary><ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p>First record in this period: {data.first_record_date || 'None'}.</p></details></>}
      </section>
      {data && <>
        <section className="workspace-operation-block"><h3>Current debtors</h3><p>Invoice-level balances across all dates; contacts are not automatically merged into one customer identity.</p>{!data.debtors.length && <p>No outstanding issued invoices in this selection.</p>}<ul className="workspace-order-list">{data.debtors.map((d) => <li key={d.invoice_id}><div><h4>{d.customer} · {money(d.outstanding)}</h4><p>{d.contact} · {d.number} · Due {d.due_on || 'Not specified'}{d.overdue ? ' · Overdue' : ''}</p></div></li>)}</ul></section>
        <section className="workspace-operation-block"><h3>Possible recurring expenses</h3><p>Unconfirmed patterns in the observed ledger. Review the supporting records before declaring a subscription.</p>{!data.recurring_candidates.length && <p>No matching recurring patterns yet. At least three regularly spaced dates with matching details and amount are needed.</p>}<ul className="workspace-order-list">{data.recurring_candidates.map((r) => <li key={r.record_ids.join('-')}><div><h4>{r.description} · {money(r.amount)} · possibly {r.cadence_candidate}</h4><p>{r.occurrences} records · {r.dates.join(', ')}</p><details><summary>Supporting record IDs</summary><p className="workspace-order-prewrap">{r.record_ids.join('\n')}</p></details></div></li>)}</ul></section>
        <section className="workspace-operation-block"><h3>Declared subscriptions & recurring commitments</h3><p>Approximate monthly commitments: {money(data.declared_monthly_commitments)}. These do not post payments or get added again to historical burn. Cancel here only records your tracking decision; contact the supplier to stop actual billing.</p>
          <ul className="workspace-order-list">{data.commitments.map((p) => <li key={p.id}><div><h4>{p.vendor} · {money(p.amount)} / {p.cadence}</h4><p>{p.description} · Next due {p.next_due} · {p.status}{p.cancel_reason ? ` · ${p.cancel_reason}` : ''}</p>{p.status === 'active' && <button className="workspace-text-button" disabled={busy} onClick={() => { const reason = window.prompt('Why are you cancelling this tracked commitment?'); if (reason) action(async () => { await api(`/businesses/${businessId}/recurring-commitments/${p.id}/cancel`, 'POST', { reason }); setVersion((v) => v + 1); }, 'Tracking cancelled with history retained. No supplier subscription was cancelled externally.'); }}>Cancel tracked commitment</button>}</div></li>)}</ul>
          <details><summary>Add a confirmed recurring commitment</summary><form className="workspace-order-form" onSubmit={addCommitment}><fieldset disabled={busy}>
            <label className="workspace-field"><span>Commitment location</span><select name="location_id" required>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label><label className="workspace-field"><span>Recurring vendor</span><input name="vendor" required minLength={2} maxLength={120} /></label><label className="workspace-field"><span>Recurring description</span><input name="description" required minLength={3} maxLength={240} /></label><label className="workspace-field"><span>Recurring amount (NGN)</span><input name="amount" type="number" required min="0.01" step="0.01" /></label><label className="workspace-field"><span>Billing cadence</span><select name="cadence"><option value="monthly">Monthly</option><option value="weekly">Weekly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></label><label className="workspace-field"><span>Next expected due date</span><input name="next_due" type="date" required defaultValue={today()} /></label><button className="workspace-secondary">Save tracked commitment</button>
          </fieldset></form></details>
        </section>
      </>}
    </>}
  </section>;
}
