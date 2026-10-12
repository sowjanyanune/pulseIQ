let csrf = "";
export function setCsrf(value: string) { csrf = value; }

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Cannot connect to the PULSEIQ backend. Check Render status, deployment logs, and /health.");
  }
  const text = await response.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { /* Render may return an HTML error page */ }
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("session-expired"));
    const detail = body?.detail;
    let message = typeof detail === "string" ? detail : "";
    if (Array.isArray(detail)) {
      message = detail.map((d: any) => {
        const field = Array.isArray(d.loc) ? String(d.loc.filter((v: any) => v !== 'body').join('.')) : 'Field';
        return `${field}: ${d.msg || 'Invalid value'}`;
      }).join('; ');
    }
    if (!message && typeof detail?.message === "string") message = detail.message;
    if (!message) message = response.status >= 500
      ? `Server error HTTP ${response.status}. Check Render Logs for this request (${options.method || "GET"} /api${path}).`
      : `Request rejected (HTTP ${response.status}). Please check the form fields.`;
    throw new Error(message);
  }
  if (body === null) throw new Error(`Unexpected non-JSON response from /api${path}. Check the backend route.`);
  return body as T;
}
export function query(values: Record<string, unknown>) {
  const q = new URLSearchParams();
  Object.entries(values).forEach(([k, v]) => {
    if (v !== "" && v !== undefined && v !== null && v !== "All") q.set(k, String(v));
  });
  return "?" + q.toString();
}
