// Local workspace API uses an HttpOnly session; identity never comes from localStorage.
export async function workspaceRequest(path, method = 'GET', body) {
  let response;
  try {
    response = await fetch(`/enterprise-api${path}`, {
      method,
      credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('The local workspace is unavailable. Check that the preview is running.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join('. ')
      : data.detail;
    const error = new Error(detail || 'The workspace could not complete this request. Please try again.');
    error.status = response.status;
    throw error;
  }
  return data;
}
