// fetch wrapper: same-origin only, JSON, CSRF header, 401 handling (the shell listens for "auth:lost").
export class ApiError extends Error { constructor(message, status, code, body) { super(message); this.status = status; this.code = code; this.body = body; } }
export const bus = new EventTarget();
let inflight = 0;
const busy = (d) => { inflight = Math.max(0, inflight + d); bus.dispatchEvent(new CustomEvent("net:inflight", { detail: { n: inflight } })); };
export const inflightCount = () => inflight;

/** Parse a Server-Timing header ("query;dur=1.2;desc=…, features;dur=40") into [{name, dur, desc}]. */
export function parseServerTiming(v) {
  if (!v) return [];
  return v.split(",").map((part) => {
    const [name, ...kv] = part.trim().split(";").map((x) => x.trim());
    const o = { name, dur: null, desc: "" };
    kv.forEach((x) => { const [k, val = ""] = x.split("="); if (k === "dur") o.dur = Number(val); else if (k === "desc") o.desc = val.replace(/^"|"$/g, ""); });
    return o;
  }).filter((x) => x.name);
}

async function fail(res, path) {
  const data = await res.json().catch(() => ({}));
  const msg = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : `${res.status} ${res.statusText}`;
  if (res.status === 401 && !path.startsWith("/api/auth/")) bus.dispatchEvent(new CustomEvent("auth:lost", { detail: { code: data.code } }));
  return new ApiError(msg, res.status, data.code, data);
}

export async function api(path, { method = "GET", body, signal, meta = false } = {}) {
  let res;
  busy(1);
  try {
    try {
      res = await fetch(path, { method, credentials: "same-origin", signal, headers: { "Content-Type": "application/json", "X-Requested-With": "irl" }, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      bus.dispatchEvent(new CustomEvent("net:down", { detail: { path } }));
      throw new ApiError("The server is not reachable. Check that it is running.", 0, "network");
    }
    if (!res.ok) throw await fail(res, path);
    const data = await res.json().catch(() => ({}));
    return meta ? { data, timing: parseServerTiming(res.headers.get("Server-Timing")) } : data;
  } finally { busy(-1); }
}
export const get = (p, o) => api(p, o);
export const post = (p, body, o) => api(p, { ...o, method: "POST", body });
export const del = (p) => api(p, { method: "DELETE" });

/** POST a binary body (a WAV recording) and get JSON back. */
export async function postBinary(path, blob, { signal, type = "audio/wav" } = {}) {
  let res;
  try { res = await fetch(path, { method: "POST", credentials: "same-origin", signal, headers: { "Content-Type": type, "X-Requested-With": "irl" }, body: blob }); }
  catch (e) { if (e.name === "AbortError") throw e; throw new ApiError("The server is not reachable. Check that it is running.", 0, "network"); }
  if (!res.ok) throw await fail(res, path);
  return res.json();
}

/** POST JSON and get a binary body back (synthesised speech). */
export async function postForBlob(path, body, { signal } = {}) {
  let res;
  try { res = await fetch(path, { method: "POST", credentials: "same-origin", signal, headers: { "Content-Type": "application/json", "X-Requested-With": "irl" }, body: JSON.stringify(body) }); }
  catch (e) { if (e.name === "AbortError") throw e; throw new ApiError("The server is not reachable. Check that it is running.", 0, "network"); }
  if (!res.ok) throw await fail(res, path);
  return res.blob();
}
