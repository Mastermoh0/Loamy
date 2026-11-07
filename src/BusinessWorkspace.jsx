import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBuilding, faLocationDot, faUsers, faArrowRight, faPlus, faArrowRightFromBracket, faCheck } from '@fortawesome/free-solid-svg-icons';
import { workspaceRequest as api } from './services/workspaceService';
import './BusinessWorkspace.css';
import WorkspaceVerification from './WorkspaceVerification';
import WorkspaceFinances from './WorkspaceFinances';
import WorkspaceOrders from './WorkspaceOrders';
import WorkspacePayments from './WorkspacePayments';
import WorkspaceExpenses from './WorkspaceExpenses';
import WorkspaceOwner from './WorkspaceOwner';

const ROLE_NAMES = { owner: 'Owner', manager: 'Manager', finance: 'Finance', front_desk: 'Front desk', staff: 'Staff' };
const ROLE_NOTES = {
  owner: 'All locations. Manages locations and team access.',
  manager: 'Manages services, orders and financial records for the assigned location.',
  finance: 'Reads orders and manages finances for the assigned location.',
  front_desk: 'Creates and cancels orders for the assigned location. No access to financial records.',
  staff: 'Submits receipts and sees their own expense history at the assigned location.',
};

function Field({ label, name, ...props }) {
  return <label className="workspace-field"><span>{label}</span><input name={name} required {...props} /></label>;
}

function AuthForm({ onReady, invitation, preview }) {
  const [creating, setCreating] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setError(''); setBusy(true);
    try {
      await api(creating ? '/register' : '/login', 'POST', values);
      await onReady();
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <div className="workspace-auth">
    <div className="workspace-intro">
      <h1>A home for every<br />part of your business.</h1>
      <p>Bring your locations and people together. Start with your business, then give each person the access they need.</p>
      <ol className="workspace-steps"><li>Name your business</li><li>Add your first location</li><li>Bring in your team</li></ol>
      <p className="workspace-local-note">{preview ? 'Local development preview. Use a test account.' : 'Sign in with your business account.'} Business accounts are separate from existing personal Loamy accounts.</p>
    </div>
    <section className="workspace-auth-form" aria-labelledby="workspace-auth-title">
      <h2 id="workspace-auth-title">{creating ? 'Create your business account' : 'Welcome back'}</h2>
      <p>{invitation ? 'Use the email your team invitation was created for.' : 'Your details come first. Business setup is next.'}</p>
      <form onSubmit={submit}>
        <fieldset disabled={busy}>
          {creating && <Field label="Your full name" name="name" autoComplete="name" minLength={2} maxLength={100} />}
          <Field label="Email address" name="email" type="email" autoComplete="email" maxLength={254} />
          <Field label="Password" name="password" type="password" autoComplete={creating ? 'new-password' : 'current-password'} minLength={10} maxLength={128} />
          <small>At least 10 characters.</small>
          {error && <p role="alert" className="workspace-error">{error}</p>}
          <button className="workspace-primary" type="submit">{busy ? 'Please wait…' : creating ? 'Continue to business setup' : 'Sign in'} <FontAwesomeIcon icon={faArrowRight} /></button>
        </fieldset>
      </form>
      <button className="workspace-text-button" onClick={() => { setCreating(!creating); setError(''); }}>
        {creating ? 'Already created a business account? Sign in' : 'New here? Create a business account'}
      </button>
    </section>
  </div>;
}

export default function BusinessWorkspace() {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(import.meta.env.DEV);
  const [selected, setSelected] = useState('');
  const [workspace, setWorkspace] = useState(null);
  const [tab, setTab] = useState('locations');
  const [financeLocation, setFinanceLocation] = useState('');
  const [addingLocation, setAddingLocation] = useState(false);
  const [newBusiness, setNewBusiness] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [invitationLink, setInvitationLink] = useState('');
  const invitation = new URLSearchParams(hash.slice(1)).get('invite') || '';
  const verification = new URLSearchParams(hash.slice(1)).get('verify') || '';

  const refresh = useCallback(async (businessId) => {
    const next = await api('/me');
    const id = businessId || next.businesses[0]?.id || '';
    const detail = id ? await api(`/businesses/${id}`) : null;
    setSession(next); setSelected(id); setWorkspace(detail);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const config = await api('/config');
        if (!cancelled) setPreview(config.local_preview);
        const next = await api('/me');
        const id = next.businesses[0]?.id || '';
        const detail = id ? await api(`/businesses/${id}`) : null;
        if (!cancelled) { setSession(next); setSelected(id); setWorkspace(detail); }
      } catch (failure) {
        if (!cancelled && failure.status !== 401) setError(failure.message);
      } finally { if (!cancelled) setLoading(false); }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  async function action(work, message) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); if (message) setNotice(message); }
    catch (failure) {
      setError(failure.message);
      if (failure.status === 401) { setSession(null); setWorkspace(null); }
    } finally { setBusy(false); }
  }

  async function createBusiness(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    await action(async () => {
      const created = await api('/businesses', 'POST', data);
      await refresh(created.id); setNewBusiness(false); setTab('locations');
    }, 'Your business and first location are ready.');
  }

  async function addLocation(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    await action(async () => {
      await api(`/businesses/${selected}/locations`, 'POST', data);
      await refresh(selected); setAddingLocation(false);
    }, 'Location added.');
  }

  async function invite(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    await action(async () => {
      const result = await api(`/businesses/${selected}/invitations`, 'POST', data);
      setInvitationLink(`${window.location.origin}/business#invite=${result.token}`);
      await refresh(selected); form.reset();
    }, 'Invitation created. No email has been sent.');
  }

  const owner = workspace?.role === 'owner';
  const canFinance = ['owner', 'manager', 'finance'].includes(workspace?.role);
  const canOrders = ['owner', 'manager', 'finance', 'front_desk'].includes(workspace?.role);
  return <div className="business-workspace">
    <a href="#workspace-content" className="workspace-skip">Skip to workspace</a>
    <header className="workspace-header">
      <Link to="/business" className="workspace-brand" aria-label="Loamy business workspace"><span aria-hidden="true">L</span>loamy<span className="workspace-brand-label">Business</span></Link>
      <div className="workspace-header-actions"><span className="workspace-preview-badge">{preview ? 'Local preview' : 'Business workspace'}</span>
        {session && <button disabled={busy} className="workspace-text-button" onClick={() => action(async () => {
          await api('/logout', 'POST'); setSession(null); setWorkspace(null); setInvitationLink(''); setNotice('');
        })}><FontAwesomeIcon icon={faArrowRightFromBracket} /> Sign out</button>}
      </div>
    </header>
    <div id="workspace-content" className="workspace-content">
      {loading ? <p role="status">Opening your workspace…</p> : <>
        {error && <p role="alert" className="workspace-error">{error}</p>}
        {notice && <p role="status" className="workspace-notice"><FontAwesomeIcon icon={faCheck} /> {notice}</p>}
        {!session ? <AuthForm onReady={() => refresh()} invitation={invitation} preview={preview} /> : !session.user.verified || verification ?
          <WorkspaceVerification session={session} token={verification} invitation={invitation} onVerified={() => refresh()} /> : <>
          <div className="workspace-topline"><p>Welcome, {session.user.name}.</p><span>{session.user.verification_method === 'capture' ? 'Email verified for local testing' : 'Email verified'}</span></div>
          {invitation && <section className="workspace-invitation">
            <h2>You have a team invitation</h2><p>Accept using the account it was created for. You are signed in as {session.user.email}.</p>
            <button disabled={busy} className="workspace-primary" onClick={() => action(async () => {
              const result = await api('/invitations/accept', 'POST', { token: invitation });
              navigate('/business', { replace: true }); await refresh(result.id);
            }, 'You have joined the business.')}>Accept invitation</button>
            <button className="workspace-text-button" onClick={() => navigate('/business', { replace: true })}>Dismiss</button>
          </section>}
          {invitation && !workspace ? null : (!workspace || newBusiness) ? <section className="workspace-setup">
            <div><h1>Let’s set up<br />your business.</h1><p>One business, as many locations as you need. Add your first location now; you can add the rest from your workspace.</p>
              <p className="workspace-local-note">{preview ? 'This preview saves on this computer. ' : ''}You can record finances for each location; live bank imports are connected separately.</p></div>
            <form onSubmit={createBusiness}><fieldset disabled={busy}>
              <Field label="Business name" name="name" placeholder="e.g. Palm House Apartments" minLength={2} maxLength={100} />
              <Field label="First location name" name="location_name" placeholder="e.g. Lekki" minLength={2} maxLength={100} />
              <Field label="Location address" name="address" autoComplete="street-address" minLength={2} maxLength={240} />
              <button className="workspace-primary" type="submit">{busy ? 'Creating…' : 'Create business'} <FontAwesomeIcon icon={faArrowRight} /></button>
              {workspace && <button type="button" className="workspace-text-button" onClick={() => setNewBusiness(false)}>Cancel</button>}
            </fieldset></form>
          </section> : <>
            <div className="workspace-title-row"><div><h1>{workspace.business.name}</h1><p>{owner ? 'Your locations and the people behind them.' : `Your assigned location · ${ROLE_NAMES[workspace.role]}`}</p></div>
              <label className="workspace-switch"><span>Switch business</span><select value={selected} disabled={busy} onChange={(e) => { const id = e.target.value; setAddingLocation(false); setInvitationLink(''); action(() => refresh(id)); }}>
                {session.businesses.map((b) => <option value={b.id} key={b.id}>{b.name}</option>)}
              </select></label></div>
            <div className="workspace-scope"><FontAwesomeIcon icon={faBuilding} /><div><strong>{ROLE_NAMES[workspace.role]} access</strong><p>{ROLE_NOTES[workspace.role]}</p></div><span>{workspace.locations.length} {workspace.locations.length === 1 ? 'location' : 'locations'}</span></div>
            <nav className="workspace-tabs" aria-label="Workspace sections">
              {owner && <button aria-current={tab === 'overview' ? 'page' : undefined} onClick={() => setTab('overview')}>Owner overview</button>}
              <button aria-current={tab === 'locations' ? 'page' : undefined} onClick={() => { setTab('locations'); setInvitationLink(''); }}><FontAwesomeIcon icon={faLocationDot} />Locations</button>
              {canFinance && <button aria-current={tab === 'finances' ? 'page' : undefined} onClick={() => { setFinanceLocation(''); setTab('finances'); }}>Financial records</button>}
              {canFinance && <button aria-current={tab === 'payments' ? 'page' : undefined} onClick={() => setTab('payments')}>Payments & balances</button>}
              <button aria-current={tab === 'expenses' ? 'page' : undefined} onClick={() => setTab('expenses')}>Expenses & receipts</button>
              {canOrders && <button aria-current={tab === 'orders' ? 'page' : undefined} onClick={() => setTab('orders')}>Services & orders</button>}
              {owner && <button aria-current={tab === 'team' ? 'page' : undefined} onClick={() => setTab('team')}><FontAwesomeIcon icon={faUsers} />Team & access</button>}
            </nav>
            {tab === 'overview' && owner ? <WorkspaceOwner key={selected} businessId={selected} locations={workspace.locations} /> : tab === 'expenses' ? <WorkspaceExpenses key={selected} businessId={selected} locations={workspace.locations} /> : tab === 'payments' && canFinance ? <WorkspacePayments key={selected} businessId={selected} locations={workspace.locations} /> : tab === 'orders' && canOrders ? <WorkspaceOrders key={selected} businessId={selected} role={workspace.role} locations={workspace.locations} /> : tab === 'finances' && canFinance ? <WorkspaceFinances key={`${selected}-${financeLocation}`} businessId={selected} role={workspace.role} locations={workspace.locations} initialLocation={financeLocation}
              onChanged={() => refresh(selected).catch((failure) => setError(failure.message))} /> : tab === 'locations' || !owner ? <section aria-labelledby="locations-title">
              <div className="workspace-section-heading"><div><h2 id="locations-title">{owner ? 'Business locations' : 'Your location'}</h2><p>{owner ? 'Each location will keep its own orders and financial activity.' : 'Your access is limited to this location.'}</p></div>
                {owner && <button className="workspace-secondary" onClick={() => setAddingLocation(!addingLocation)}><FontAwesomeIcon icon={faPlus} /> {addingLocation ? 'Close form' : 'Add location'}</button>}
              </div>
              {addingLocation && owner && <form className="workspace-inline-form" onSubmit={addLocation}><fieldset disabled={busy}>
                <Field label="Location name" name="name" minLength={2} maxLength={100} /><Field label="Address" name="address" minLength={2} maxLength={240} />
                <button className="workspace-primary" type="submit">{busy ? 'Saving…' : 'Save location'}</button>
              </fieldset></form>}
              <ul className="workspace-locations">{workspace.locations.map((location) => <li key={location.id}>
                <span className="workspace-location-icon"><FontAwesomeIcon icon={faLocationDot} /></span><div><h3>{location.name}</h3><p>{location.address}</p></div>{canFinance && <button className="workspace-text-button workspace-location-state" onClick={() => { setFinanceLocation(location.id); setTab('finances'); }}>View financial records</button>}
              </li>)}</ul>
              <div className="workspace-next"><h3>{canOrders ? 'Your front desk is ready' : 'Your location workspace'}</h3><p>{canOrders ? 'Use Services & orders for customers, Payments & balances for finance review, and Expenses & receipts for staff submissions.' : 'Open Expenses & receipts to submit evidence and follow your review history.'}</p></div>
              {owner && <button className="workspace-text-button" onClick={() => setNewBusiness(true)}>Set up another business</button>}
            </section> : <section aria-labelledby="team-title">
              <div className="workspace-section-heading"><div><h2 id="team-title">People & permissions</h2><p>Team members receive access to one assigned location.</p></div></div>
              <div className="workspace-team-layout"><div>
                <ul className="workspace-team">{workspace.team.map((member) => <li key={member.id}><span className="workspace-avatar">{member.name.slice(0, 1).toUpperCase()}</span>
                  <div><h3>{member.name}</h3><p>{member.email}</p><small>{ROLE_NAMES[member.role]} · {member.location || 'All locations'}</small></div>
                  {member.role !== 'owner' && <button className="workspace-text-button" disabled={busy} aria-label={`Remove ${member.name}`} onClick={() => {
                    if (window.confirm(`Remove ${member.name}'s access to this business?`)) action(async () => { await api(`/businesses/${selected}/members/${member.id}`, 'DELETE'); await refresh(selected); }, 'Team access removed.');
                  }}>Remove</button>}
                </li>)}</ul>
                {workspace.invitations.length > 0 && <div className="workspace-pending"><h3>Pending invitations</h3>{workspace.invitations.map((item) => <p key={item.id}>{item.email} <span>{ROLE_NAMES[item.role]}</span></p>)}</div>}
              </div><form className="workspace-invite-form" onSubmit={invite}><fieldset disabled={busy}>
                <h3>Invite a team member</h3><Field label="Team member email" name="email" type="email" maxLength={254} />
                <label className="workspace-field"><span>Role</span><select name="role" defaultValue="front_desk">{Object.entries(ROLE_NAMES).filter(([key]) => key !== 'owner').map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
                <label className="workspace-field"><span>Assigned location</span><select name="location_id" required>{workspace.locations.map((l) => <option value={l.id} key={l.id}>{l.name}</option>)}</select></label>
                <button type="submit" className="workspace-primary">{busy ? 'Creating…' : 'Create invitation link'}</button>
                <small>Links expire after 72 hours. The recipient must verify their account before joining. Copy the link to share; invitations are not emailed automatically.</small>
                {invitationLink && <label className="workspace-field"><span>Invitation link — copy to test</span><input className="selectable" readOnly value={invitationLink} onFocus={(e) => e.target.select()} /></label>}
              </fieldset></form></div>
              <section className="workspace-audit"><h3>Access history</h3><ul>{workspace.events.map((item, i) => <li key={`${item.created_at}-${i}`}><div>{item.action}<small>{item.actor}</small></div><time dateTime={new Date(item.created_at * 1000).toISOString()}>{new Date(item.created_at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</time></li>)}</ul></section>
            </section>}
          </>}
        </>}
      </>}
    </div>
    <footer className="workspace-footer"><span>Loamy · Business workspace</span>{import.meta.env.VITE_ENTERPRISE_ONLY !== 'true' && <Link to="/">Individual business sign-in</Link>}</footer>
  </div>;
}
