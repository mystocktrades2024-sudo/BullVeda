// stale-stamp.jsx — live "last computed" timestamp that ages and flips to a STALE
// state past a threshold, with a recompute affordance. Used on data-sensitive
// surfaces (Risk, Internals) where staleness materially changes the read.
const { useState: useStampS, useEffect: useStampE } = React;

function StaleStamp({ staleAfter = 60, label = "computed", src }) {
  const [base, setBase] = useStampS(() => Date.now());
  const [, tick] = useStampS(0);
  useStampE(() => {
    const t = setInterval(() => tick(x => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const ageS = Math.floor((Date.now() - base) / 1000);
  const stale = ageS >= staleAfter;
  const warming = !stale && ageS >= staleAfter * 0.66;
  const state = stale ? "stale" : warming ? "warm" : "live";
  const fmtAge = ageS < 60 ? `${ageS}s` : `${Math.floor(ageS / 60)}m ${String(ageS % 60).padStart(2, "0")}s`;
  const time = new Date(base).toLocaleTimeString("en-US", { hour12: false }) + " ET";
  return (
    <div className={`stamp stamp--${state}`}>
      <span className="stamp-dot" />
      <span className="mono stamp-state">{stale ? "STALE" : warming ? "AGING" : "LIVE"}</span>
      <span className="mono stamp-meta">{label} {time} · {fmtAge} ago</span>
      {(stale || warming) && (
        <button className="stamp-recompute mono" onClick={() => setBase(Date.now())} title="Re-run the pipeline">↻ recompute</button>
      )}
      {src && <span className="mono stamp-src">{src}</span>}
    </div>
  );
}
window.StaleStamp = StaleStamp;
