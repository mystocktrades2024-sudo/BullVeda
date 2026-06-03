// surface-etfs.jsx — unified ETFs surface: Sector Rotation + ETF Screener tabs.

const { useState: useETFs } = React;

function SurfaceETFs({ onTicker }) {
  const [tab, setTab] = useETFs("sector");
  return (
    <div className="etfs-wrap">
      <div className="etfs-tabbar">
        <div className="etfs-tabs">
          <button className={`etfs-tab ${tab === "sector" ? "is-on" : ""}`} onClick={() => setTab("sector")}>
            <span className="etfs-tab-l">Sector Rotation</span>
            <span className="etfs-tab-s mono dim2">11 GICS SPDRs · RRG</span>
          </button>
          <button className={`etfs-tab ${tab === "screener" ? "is-on" : ""}`} onClick={() => setTab("screener")}>
            <span className="etfs-tab-l">ETF Screener</span>
            <span className="etfs-tab-s mono dim2">96 funds · all categories</span>
          </button>
        </div>
      </div>
      {tab === "sector"
        ? <SurfaceSector onTicker={onTicker} />
        : <SurfaceEtfScreener onTicker={onTicker} />}
    </div>
  );
}

window.SurfaceETFs = SurfaceETFs;
