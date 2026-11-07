import { useEffect, useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';

const money = (value) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);

export default function WorkspaceOwner({ businessId, locations }) {
  const [filters, setFilters] = useState({ location_id: '', start: '', end: '' });
  const [query, setQuery] = useState(''), [version, setVersion] = useState(0);
  const [data, setData] = useState(null), [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api(`/businesses/${businessId}/owner-dashboard?${query}`).then((result) => {
      if (active) setData(result);
    }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [businessId, query, version]);
  function filter(event) {
    event.preventDefault();
    setData(null); setError('');
    setQuery(new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString());
    setVersion((v) => v + 1);
  }
  return <section aria-labelledby="owner-title">
    <div className="workspace-section-heading"><div><h2 id="owner-title">Owner overview</h2><p>Your locations, cash movement and money still owed.</p></div></div>
    <form className="workspace-owner-filters" onSubmit={filter}>
      <label className="workspace-field"><span>Location</span><select value={filters.location_id} onChange={(e) => setFilters({ ...filters, location_id: e.target.value })}><option value="">All locations</option>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
      <label className="workspace-field"><span>From</span><input type="date" value={filters.start} onChange={(e) => setFilters({ ...filters, start: e.target.value })} /></label>
      <label className="workspace-field"><span>Through</span><input type="date" value={filters.end} onChange={(e) => setFilters({ ...filters, end: e.target.value })} /></label>
      <button className="workspace-secondary" type="submit">Update overview</button>
    </form>
    {error && <p role="alert" className="workspace-error">{error}</p>}
    {!data && !error && <p role="status">Loading your overview…</p>}
    {data && <>
      <p className="workspace-local-note">Recorded activity · {data.period.start} to {data.period.end} · Lagos time. Leave dates blank for the last 30 days.</p>
      <div className="workspace-owner-metrics">
        {[['Money in', data.totals.inflow], ['Money out', data.totals.outflow], ['Net movement', data.totals.net], ['Currently owed', data.totals.outstanding]].map(([label, value]) => <article key={label}><h3>{label}</h3><strong>{money(value)}</strong><small>{label === 'Currently owed' ? 'All issued invoices, current balance' : 'Posted records in selected dates'}</small></article>)}
      </div>
      <p>{data.totals.records} posted records · {data.totals.open_orders} open orders in this period · {money(data.totals.order_value)} order value. Order value is shown separately from money received.</p>
      <p><strong>{money(data.totals.payables)}</strong> currently owed to suppliers · {money(data.totals.overdue_payables)} overdue. Unpaid bills are separate from cash outflow and customer money owed.</p>
      <div className="workspace-owner-attention"><p><strong>{money(data.totals.overdue)}</strong> currently overdue · {data.totals.unpaid_invoices} invoices with a balance · {money(data.totals.overpayment)} excess allocations</p><p>{data.totals.pending_review} expenses awaiting review · {data.totals.approved_unposted} approved, awaiting posting</p></div>
      <h3>By location</h3>
      <ul className="workspace-owner-locations">{data.locations.map((l) => <li key={l.id}><h4>{l.name}</h4><dl>{[['Money in', money(l.inflow)], ['Money out', money(l.outflow)], ['Net movement', money(l.net)], ['Currently owed', money(l.outstanding)], ['Owed to suppliers', money(l.payables)], ['Open orders', l.open_orders], ['Expenses to review', l.pending_review]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></li>)}</ul>
      <h3>Receiving accounts</h3><p>{data.coverage.account_scope}</p>
      {data.accounts.length ? <ul className="workspace-owner-accounts">{data.accounts.map((a) => <li key={a.id}><h4>{a.name} · {a.location}</h4><p>{a.reference}</p><dl><div><dt>Recorded credits</dt><dd>{money(a.recorded_credits)}</dd></div><div><dt>Allocated</dt><dd>{money(a.allocated)}</dd></div><div><dt>Unallocated</dt><dd>{money(a.unallocated)}</dd></div></dl></li>)}</ul> : <p>No receiving accounts in this selection. Add one in Payments & balances.</p>}
      <details><summary>What these figures include</summary><p>{data.coverage.flow_scope}</p><p>{data.coverage.receivables_scope}</p><p>No live bank feed is connected. Values reflect recorded activity and may be incomplete.</p><p>Record sources: {Object.entries(data.coverage.sources).map(([source, count]) => `${source.replaceAll('_', ' ')} (${count})`).join(', ') || 'No posted activity in this period'}.</p><p>Updated {new Date(data.coverage.generated_at * 1000).toLocaleString('en-GB')}.</p></details>
    </>}
  </section>;
}
