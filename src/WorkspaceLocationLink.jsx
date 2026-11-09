import { useState } from 'react';
import { workspaceRequest as api } from './services/workspaceService';

export default function WorkspaceLocationLink({ businessId, location }) {
  const [link, setLink] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <div className="workspace-location-link"><button className="workspace-text-button" disabled={busy} onClick={async () => { if (link) { setLink(null); return; } setBusy(true); setError(''); try { setLink(await api(`/businesses/${businessId}/locations/${location.id}/link`)); } catch (failure) { setError(failure.message); } finally { setBusy(false); } }}>{busy ? 'Preparing QR…' : link ? 'Hide location QR' : 'Show location QR'}</button>
    {error && <p role="alert" className="workspace-error">{error}</p>}
    {link && <div><h4>{location.name} location link</h4><img className="workspace-location-qr" src={link.qr_data_url} alt={`QR code for ${location.name} workspace`} width="240" height="240" /><p>Scan to open this location after sign-in. This is a navigation shortcut; it grants no access and is not a team invitation.</p><p>{link.url.startsWith('http://127.0.0.1') && 'Local preview: this address works only on this computer. A phone scan needs Samuel’s HTTPS deployment.'}</p><label className="workspace-field"><span>Location link — select to copy</span><input readOnly value={link.url} onFocus={(event) => event.target.select()} /></label><div className="workspace-order-actions"><a href={link.url} className="workspace-text-button">Open location link</a><a href={link.qr_data_url} download={`loamy-location-${location.id}.svg`} className="workspace-secondary">Download QR code</a></div></div>}
  </div>;
}
