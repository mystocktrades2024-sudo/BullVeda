// ai-explain.jsx — reusable "Explain with AI" button + output. window.AiExplain.
// Keeps the host panel's MATH deterministic; the LLM only does the plain-English
// wording. A shared guard enforces plain text + the "not advice" compliance rule.
// Prototype: window.claude.complete (haiku). Production: your Kairos/Gemini proxy.

(function () {
  const css = `
  .aix { display:flex; flex-direction:column; gap:6px; }
  .aix-btn { align-self:flex-start; cursor:pointer; font:700 9.5px var(--mono); letter-spacing:0.04em;
    color:var(--cy); background:color-mix(in oklab, var(--cy) 10%, transparent);
    border:1px solid color-mix(in oklab, var(--cy) 38%, transparent); border-radius:999px; padding:4px 11px; }
  .aix-btn:hover { background:color-mix(in oklab, var(--cy) 18%, transparent); }
  .aix-btn:disabled { opacity:0.6; cursor:default; }
  .aix-out { display:flex; flex-direction:column; gap:5px; padding:10px 12px; margin-top:1px;
    background:color-mix(in oklab, var(--cy) 7%, transparent);
    border:1px solid color-mix(in oklab, var(--cy) 26%, transparent); border-radius:6px; }
  .aix-tag { font:700 8.5px var(--mono); letter-spacing:0.1em; color:var(--cy); }
  .aix-txt { font-size:12.5px; line-height:1.6; color:var(--ink-1); white-space:pre-wrap; }`;
  if (!document.getElementById("aix-css")) {
    const s = document.createElement("style"); s.id = "aix-css"; s.textContent = css; document.head.appendChild(s);
  }
})();

// Shared call helper — wraps the LLM with the plain-text + "not advice" guard.
// Returns { ok, text }. Lets panels place the button/output wherever they want.
window.aiComplete = async (base) => {
  const guard = "\n\nWrite PLAIN TEXT ONLY — no markdown, no headings, no # or ** symbols, no bullet characters. Keep it short, simple, and jargon-free. This is informational/educational ONLY — do NOT tell anyone to buy or sell, and add no disclaimer.";
  const prompt = String(base || "") + guard;
  // 1) claude.ai preview hook (only present inside the claude.ai canvas)
  if (window.claude && window.claude.complete) {
    try { const t = await window.claude.complete(prompt); return { ok: true, text: (t || "").trim() || "—" }; } catch (e) {}
  }
  // 2) REAL backend LLM via /api/chat (local Ollama, SSE-streamed token-by-token)
  try {
    const res = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ message: prompt, ticker: (window.__BV && window.__BV._aiTicker) || null }),
    });
    if (res.status === 503) return { ok: false, text: "AI explainer is turned off on this server (AI_CHAT_ENABLED=0)." };
    if (!res.ok || !res.body) throw new Error("chat " + res.status);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "", out = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) {
        const line = p.trim();
        if (!line.startsWith("data:")) continue;
        const js = line.slice(5).trim();
        if (!js) continue;
        try { const o = JSON.parse(js); if (o.token) out += o.token; if (o.error) throw new Error(o.error); } catch (e) { if (/error/.test(String(e.message))) throw e; }
      }
    }
    out = out.trim();
    return out ? { ok: true, text: out } : { ok: false, text: "The AI explainer returned no text — try again." };
  } catch (e) {
    return { ok: false, text: "AI explainer isn't reachable right now (local model offline). The summary above still applies." };
  }
};

// <AiExplain build={() => "prompt string built from live numbers"} label="…" tag="KAIROS" />
function AiExplain({ build, label = "Explain with AI", tag = "KAIROS" }) {
  const [ai, setAi] = React.useState(null);   // null | "loading" | text
  const run = async () => {
    setAi("loading");
    const base = typeof build === "function" ? build() : build;
    const res = await window.aiComplete(base);
    setAi(res.text);
  };
  return (
    <div className="aix">
      <button className="aix-btn mono" onClick={run} disabled={ai === "loading"}>
        {ai === "loading" ? "✦ thinking…" : "✦ " + label}
      </button>
      {ai && ai !== "loading" && (
        <div className="aix-out mono">
          <span className="aix-tag">✦ {tag}</span>
          <span className="aix-txt">{ai}</span>
        </div>
      )}
    </div>
  );
}
window.AiExplain = AiExplain;
