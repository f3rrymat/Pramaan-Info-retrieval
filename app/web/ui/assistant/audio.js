// Voice input and spoken replies for the assistant. No network calls except to this server (/api/assistant/*).
// Recording: MediaRecorder captures the microphone; the browser's container (WebM/Opus in Chromium) is decoded and
// re-encoded here as 16 kHz mono 16-bit WAV, which Sarvam accepts and our server can check for length (30 s limit).
// Speaking: replies are read sentence by sentence (the first sentence alone, so speech starts early), one <audio> element,
// next clip fetched while the current one plays. stop() halts at once and drops the queue; the text stays on screen.
import { postForBlob } from "/ui/api.js";

const SR = 16000;

/** Encode mono Float32 samples as 16-bit PCM WAV. */
export function encodeWav(samples, rate = SR) {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i += 1) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0, o = 44; i < samples.length; i += 1, o += 2) { const s = Math.max(-1, Math.min(1, samples[i])); v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true); }
  return new Blob([buf], { type: "audio/wav" });
}

/** Decode any recorded blob and resample it to 16 kHz mono WAV. */
export async function toWav16k(blob) {
  const AC = window.AudioContext || window.webkitAudioContext;
  const ctx = new AC();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const len = Math.max(1, Math.ceil(decoded.duration * SR));
    const off = new OfflineAudioContext(1, len, SR);
    const src = off.createBufferSource(); src.buffer = decoded; src.connect(off.destination); src.start();
    const out = await off.startRendering();
    return { wav: encodeWav(out.getChannelData(0), SR), seconds: decoded.duration };
  } finally { ctx.close().catch(() => {}); }
}

export const canRecord = () => !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder && (window.AudioContext || window.webkitAudioContext) && window.OfflineAudioContext);

/** Microphone recorder with a live level meter and an automatic stop at maxSeconds. */
export class Recorder {
  constructor({ maxSeconds = 30, onTick, onLevel, onAutoStop } = {}) { Object.assign(this, { maxSeconds, onTick, onLevel, onAutoStop }); this.active = false; }
  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    const AC = window.AudioContext || window.webkitAudioContext;
    this.ac = new AC();
    const srcNode = this.ac.createMediaStreamSource(this.stream);
    this.an = this.ac.createAnalyser(); this.an.fftSize = 1024; srcNode.connect(this.an);
    this.data = new Uint8Array(this.an.fftSize);
    this.chunks = [];
    this.mr = new MediaRecorder(this.stream);
    this.mr.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data); };
    this.done = new Promise((res) => { this.mr.onstop = () => res(new Blob(this.chunks, { type: this.mr.mimeType || "audio/webm" })); });
    this.mr.start(250);
    this.t0 = performance.now(); this.active = true;
    const loop = () => {
      if (!this.active) return;
      this.an.getByteTimeDomainData(this.data);
      this.onLevel && this.onLevel(this.data);
      const el = (performance.now() - this.t0) / 1000;
      this.onTick && this.onTick(el, Math.max(0, this.maxSeconds - el));
      if (el >= this.maxSeconds) { this.onAutoStop && this.onAutoStop(); return; }
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }
  _release() { this.active = false; cancelAnimationFrame(this.raf); this.stream?.getTracks().forEach((t) => t.stop()); this.ac?.close().catch(() => {}); }
  /** Stop and return {wav, seconds}. */
  async stop() { if (!this.mr) return null; const was = this.mr.state !== "inactive"; if (was) this.mr.stop(); const blob = await this.done; this._release(); return toWav16k(blob); }
  cancel() { try { if (this.mr && this.mr.state !== "inactive") this.mr.stop(); } catch (_) { /* ignore */ } this._release(); }
}

/** Split a reply into speakable segments: the first sentence alone, then groups of about `max` characters. */
export function segments(text, max = 360) {
  const clean = text.replace(/```[\s\S]*?```/g, " ").replace(/[*_`#>|]/g, " ").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  const sents = clean.split(/(?<=[.!?।॥])\s+|\n+/).map((s) => s.trim()).filter(Boolean);
  const out = [];
  sents.forEach((s, i) => { if (i === 0 || !out.length) out.push(s); else if (out.length > 1 && out[out.length - 1].length + s.length + 1 <= max) out[out.length - 1] += ` ${s}`; else out.push(s); });
  return out;
}

/** Sentence-by-sentence speech through /api/assistant/tts with one shared <audio> element. */
export class Speaker extends EventTarget {
  constructor() { super(); this.audio = new Audio(); this.audio.preload = "auto"; this.state = "idle"; this.gen = 0; this.urls = new Set(); }
  _set(state, extra = {}) { this.state = state; this.dispatchEvent(new CustomEvent("state", { detail: { state, ...extra } })); }
  get speaking() { return this.state === "speaking" || this.state === "loading" || this.state === "blocked"; }
  async speak(text, language, { msgId } = {}) {
    this.stop();
    const gen = ++this.gen, segs = segments(text);
    if (!segs.length) return;
    this.ctrl = new AbortController();
    this.msgId = msgId;
    this._set("loading", { msgId });
    const fetchSeg = (i) => (i < segs.length ? postForBlob("/api/assistant/tts", { text: segs[i], language }, { signal: this.ctrl.signal }).then((b) => { const u = URL.createObjectURL(b); this.urls.add(u); return u; }) : Promise.resolve(null));
    let next = fetchSeg(0);
    try {
      for (let i = 0; i < segs.length; i += 1) {
        const url = await next;
        if (gen !== this.gen || !url) return;
        next = fetchSeg(i + 1); next.catch(() => {});              // prefetch while this one plays
        await this._play(url, gen, { msgId, index: i, total: segs.length });
        if (gen !== this.gen) return;
      }
      if (gen === this.gen) this._set("idle", { msgId, finished: true });
    } catch (e) {
      if (gen !== this.gen || e.name === "AbortError") return;
      this._set("error", { msgId, message: e.message || String(e) });
    } finally { if (gen === this.gen) this._cleanup(); }
  }
  _play(url, gen, info) {
    return new Promise((resolve, reject) => {
      const a = this.audio;
      a.onended = () => resolve();
      a.onerror = () => reject(new Error("The audio could not be played."));
      this._resolve = resolve;
      a.src = url;
      this._set("speaking", info);
      a.play().catch((e) => {
        if (gen !== this.gen) return resolve();
        if (e && e.name === "NotAllowedError") { this._pending = () => a.play().then(() => this._set("speaking", info)).catch((x) => reject(x)); this._set("blocked", info); }
        else if (e && e.name === "AbortError") resolve();
        else reject(e);
      });
    });
  }
  /** Called from a user gesture ("Tap to play") after the browser blocked autoplay. */
  resume() { const p = this._pending; this._pending = null; if (p) p(); }
  stop() {
    this.gen += 1;
    try { this.ctrl?.abort(); } catch (_) { /* ignore */ }
    this.audio.pause(); this.audio.removeAttribute("src"); try { this.audio.load(); } catch (_) { /* ignore */ }
    this._pending = null;
    if (this._resolve) { const r = this._resolve; this._resolve = null; r(); }
    this._cleanup();
    if (this.state !== "idle") this._set("idle", { msgId: this.msgId, stopped: true });
  }
  _cleanup() { this.urls.forEach((u) => URL.revokeObjectURL(u)); this.urls.clear(); }
}
