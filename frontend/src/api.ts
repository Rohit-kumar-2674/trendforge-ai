let accessToken = '';
export function setAccessToken(token: string) { accessToken = token; }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...options.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'The server could not complete the request.' }));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export async function download(path: string, filename: string, token?: string) {
  const response = await fetch(path, { headers: (token || accessToken) ? { Authorization: `Bearer ${token || accessToken}` } : {} });
  if (!response.ok) throw new Error('Download failed; check your API access token.');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
}
