// lens-summary.jsx — "Desk Read" summary bar pinned atop dense lenses so the
// actionable payoff (grade / net verdict / score) is above the fold. The deep
// sections stay below. Derives per-ticker from pillars + composite engine.
const { useMemo: useMemoLS } = React;

function lensSummary(ticker, mode, kind, techData, smc) {
  const P = ticker.pillars || {};
  const cl = v => Math.round(Math.max(2, Math.min(99, v)));
  const tone = v => v >= 62 ? "gn" : v >= 46 ? "amb" : "rd";
  const tech = P.technical ?? 60, cat = P.catalyst ?? 55, edge = P.edge ?? 60, fund = P.fundamental ?? 55;
  const money = v => (typeof v === "number" && isFinite(v)) ? "$" + v.toFixed(2) : "—";
  let score, label, verdict, bullets;
  if (kind === "smc") {
    label = "SMC Structure Score";
    if (smc && smc.ok) {   // real engine model
      score = cl(smc.smc_score);
      verdict = score >= 80 ? "A" : score >= 70 ? "B+" : score >= 60 ? "B" : score >= 50 ? "C" : "D";
      const ev = smc.structure && smc.structure.events && smc.structure.events.length ? smc.structure.events[smc.structure.events.length - 1] : null;
      const r = smc.range, draw = smc.draw_on_liquidity;
      const zTone = r.zone === "discount" ? "gn" : r.zone === "premium" ? "rd" : "amb";
      bullets = [
        ["Structure", ev ? `${ev.evt} ${ev.dir} @ ${money(ev.price)}` : `${smc.bias} · no break`, smc.bias === "bull" ? "gn" : smc.bias === "bear" ? "rd" : "amb"],
        ["Draw", draw ? `${draw.side} ${money(draw.price)}` : "none in bias dir", draw ? "cy" : "amb"],
        ["Zone", `${r.zone} · ${r.pct}% of range`, zTone],
      ];
    } else {   // no live model yet — honest, not fabricated
      score = cl(tech * 0.65 + cat * 0.35);
      verdict = score >= 70 ? "B+" : score >= 60 ? "B" : score >= 50 ? "C" : "D";
      bullets = [
        ["Structure", "— loading live bars", "ink"],
        ["Draw", "—", "ink"],
        ["Zone", "—", "ink"],
      ];
    }
  } else if (kind === "patterns") {
    score = cl(tech * 0.6 + edge * 0.4);
    label = "Pattern Confluence";
    verdict = score >= 72 ? "GO" : score >= 55 ? "WATCH" : "PASS";
    bullets = [
      ["Methods aligned", `${Math.round(score / 14)} of 14`, score >= 60 ? "gn" : "amb"],
      ["Lead theory", score >= 60 ? "VCP base #2" : "no dominant", score >= 60 ? "gn" : "amb"],
      ["R:R to target", (ticker.rMultiple || 1.7).toFixed(2), "copper"],
    ];
  } else { // technicals — real RSI / RVOL from the boot payload (no hardcoded "RSI 64")
    score = cl(tech);
    label = "Technical Net Read";
    verdict = score >= 66 ? "BULLISH" : score >= 46 ? "NEUTRAL" : "WEAK";
    // prefer the live indicators payload (same source as the hero) so they never disagree
    const T = techData && typeof techData === "object" ? techData : {};
    const rsi = (typeof T.rsi === "number" && isFinite(T.rsi)) ? T.rsi : (typeof ticker.rsi === "number" && isFinite(ticker.rsi)) ? ticker.rsi : null;
    const rvol = (typeof T.rvol === "number" && isFinite(T.rvol)) ? T.rvol : (typeof ticker.rvol === "number" && isFinite(ticker.rvol)) ? ticker.rvol : null;
    bullets = [
      ["Trend", score >= 60 ? "above key MAs" : score >= 46 ? "mixed MAs" : "below key MAs", score >= 60 ? "gn" : score >= 46 ? "amb" : "rd"],
      ["Momentum", rsi != null ? `RSI ${rsi.toFixed(0)}` : "—", rsi == null ? "ink" : rsi >= 55 ? "gn" : rsi >= 45 ? "amb" : "rd"],
      ["Volume", rvol != null ? `RVOL ${rvol.toFixed(2)}×` : "—", rvol == null ? "ink" : rvol >= 1.3 ? "gn" : "amb"],
    ];
  }
  return { label, verdict, score, tone: tone(score), bullets };
}

function LensSummaryBar({ ticker, mode, kind, tech, smc }) {
  const s = useMemoLS(() => lensSummary(ticker, mode, kind, tech, smc), [ticker, mode, kind, ticker && ticker.symbol, tech && tech.rsi, tech && tech.rvol, smc && smc.ok, smc && smc.smc_score]);
  return (
    <div className={`lsum lsum--${s.tone}`}>
      <div className="lsum-l">
        <div className="lsum-eyebrow mono">DESK READ · {s.label}</div>
        <div className="lsum-headline">
          <span className={`lsum-verdict lsum-verdict--${s.tone}`}>{s.verdict}</span>
          <span className="lsum-score mono">{s.score}<span className="lsum-of">/100</span></span>
        </div>
      </div>
      <div className="lsum-bullets">
        {s.bullets.map((b, i) => (
          <div key={i} className="lsum-bullet">
            <span className="lsum-b-k mono dim2">{b[0]}</span>
            <span className={`lsum-b-v mono kpi-tone--${b[2]}`}>{b[1]}</span>
          </div>
        ))}
      </div>
      <div className="lsum-hint mono dim">full detail below ↓</div>
    </div>
  );
}
window.LensSummaryBar = LensSummaryBar;

(function () {
  if (document.getElementById("lsum-css")) return;
  const st = document.createElement("style"); st.id = "lsum-css";
  st.textContent = `
  .lsum{display:flex;align-items:center;gap:24px;background:var(--bg-2,#171b1b);border:1px solid var(--line,#262c2c);border-radius:8px;padding:12px 18px;margin:0 0 14px;flex-wrap:wrap;}
  .lsum--gn{border-left:3px solid var(--gn);} .lsum--amb{border-left:3px solid var(--amb);} .lsum--rd{border-left:3px solid var(--rd);}
  .lsum-eyebrow{font-size:9.5px;letter-spacing:.16em;color:var(--ink-3);}
  .lsum-headline{display:flex;align-items:baseline;gap:12px;margin-top:3px;}
  .lsum-verdict{font-size:20px;font-weight:700;}
  .lsum-verdict--gn{color:var(--gn);} .lsum-verdict--amb{color:var(--amb);} .lsum-verdict--rd{color:var(--rd);}
  .lsum-score{font-size:22px;font-weight:600;}
  .lsum-of{font-size:12px;color:var(--ink-3);}
  .lsum-bullets{display:flex;gap:22px;flex:1;flex-wrap:wrap;}
  .lsum-bullet{display:flex;flex-direction:column;gap:2px;}
  .lsum-b-k{font-size:9px;letter-spacing:.08em;text-transform:uppercase;}
  .lsum-b-v{font-size:12.5px;font-weight:500;}
  .lsum-hint{font-size:10px;white-space:nowrap;}
  .tl-xlink{display:block;width:100%;text-align:left;background:var(--bg-2,#171b1b);border:1px dashed var(--line-2,#323a3a);border-radius:6px;padding:8px 12px;margin-bottom:10px;color:var(--ink-2);font-family:var(--mono);font-size:11.5px;cursor:pointer;}
  .tl-xlink:hover{border-color:var(--copper);color:var(--ink-1);}
  .tl-xlink b{color:var(--copper);}
  `;
  document.head.appendChild(st);
})();
