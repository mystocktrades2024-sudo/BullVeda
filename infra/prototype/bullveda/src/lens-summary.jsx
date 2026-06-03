// lens-summary.jsx — "Desk Read" summary bar pinned atop dense lenses so the
// actionable payoff (grade / net verdict / score) is above the fold. The deep
// sections stay below. Derives per-ticker from pillars + composite engine.
const { useMemo: useMemoLS } = React;

function lensSummary(ticker, mode, kind) {
  const P = ticker.pillars || {};
  const cl = v => Math.round(Math.max(2, Math.min(99, v)));
  const tone = v => v >= 62 ? "gn" : v >= 46 ? "amb" : "rd";
  const tech = P.technical ?? 60, cat = P.catalyst ?? 55, edge = P.edge ?? 60, fund = P.fundamental ?? 55;
  let score, label, verdict, bullets;
  if (kind === "smc") {
    score = cl(tech * 0.65 + cat * 0.35);
    const grade = score >= 80 ? "A" : score >= 70 ? "B+" : score >= 60 ? "B" : score >= 50 ? "C" : "D";
    label = "SMC Entry Grade";
    verdict = grade;
    bullets = [
      ["Structure", score >= 60 ? "bullish BoS · OB holding" : "no clean shift", score >= 60 ? "gn" : "amb"],
      ["Liquidity", "buy-side swept · resting above", "gn"],
      ["OTE / zone", score >= 55 ? "in discount 62–79%" : "premium — wait", score >= 55 ? "gn" : "amb"],
    ];
  } else if (kind === "patterns") {
    score = cl(tech * 0.6 + edge * 0.4);
    label = "Pattern Confluence";
    verdict = score >= 72 ? "GO" : score >= 55 ? "WATCH" : "PASS";
    bullets = [
      ["Methods aligned", `${Math.round(score / 14)} of 14`, score >= 60 ? "gn" : "amb"],
      ["Lead theory", score >= 60 ? "VCP base #2" : "no dominant", score >= 60 ? "gn" : "amb"],
      ["R:R to target", (ticker.rMultiple || 1.7).toFixed(2), "copper"],
    ];
  } else { // technicals
    score = cl(tech);
    label = "Technical Net Read";
    verdict = score >= 66 ? "BULLISH" : score >= 46 ? "NEUTRAL" : "WEAK";
    bullets = [
      ["Trend", score >= 60 ? "stacked-bull EMAs" : "mixed MAs", score >= 60 ? "gn" : "amb"],
      ["Momentum", score >= 55 ? "RSI 64 · MACD+" : "fading", score >= 55 ? "gn" : "amb"],
      ["Volume", "RVOL 1.3× · OBV up", "gn"],
    ];
  }
  return { label, verdict, score, tone: tone(score), bullets };
}

function LensSummaryBar({ ticker, mode, kind }) {
  const s = useMemoLS(() => lensSummary(ticker, mode, kind), [ticker, mode, kind, ticker && ticker.symbol]);
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
