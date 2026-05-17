// subtabs/ml_edge/levels.js — §4 SHAP feature attributions + reconciliation note + footer.

function _shapRows(items, side) {
  if (!Array.isArray(items) || items.length === 0) {
    return `<div style="font-size:12px;color:var(--ink-3);font-family:var(--mono);padding:8px 0;">No attribution available.</div>`;
  }
  return items.map(it => {
    const v   = +it.shap || 0;
    const sgn = v >= 0 ? '+' : '−';
    const w   = Math.min(50, Math.abs(v) * 100);
    const cls = side === 'pos' ? 'pos' : 'neg';
    return `
      <div class="rk-feat-row">
        <div class="rk-feat-name">${it.feature}</div>
        <div class="rk-feat-bar">
          <div class="rk-feat-mid"></div>
          <div class="rk-feat-fill ${cls}" style="width:${w}%"></div>
        </div>
        <div class="rk-feat-val ${cls}">${sgn}${Math.abs(v).toFixed(3)}</div>
      </div>`;
  }).join('');
}

export function buildShapAndRecon(ctx) {
  const { payload, T, model } = ctx;
  const shap = (payload.shap || {}).dir_top || [];
  const pos = shap.filter(x => +x.shap >= 0);
  const neg = shap.filter(x => +x.shap < 0);

  const dir = payload.direction || {};
  const mag = payload.magnitude || {};
  const hit = payload.hit_net || {};

  const score = T.score;
  const rr    = T.rr_ratio || (T.canonical_trade_plan || {}).rr_ratio;
  const setup = T.setup_family || T.setup_type;
  const decision = T.decision || T.verdict;
  const erDays = (T.earnings || {}).days_to_earnings;

  // Reconciliation narrative
  const dirAgrees = (decision === 'BUY' && dir.p_up > dir.p_dn) || (decision === 'AVOID' && dir.p_dn > dir.p_up);
  const hitAgrees = hit.p_t1_first != null && hit.p_t1_first >= 0.55;
  const allAgree = dirAgrees && hitAgrees;

  let reconCls, reconText;
  if (allAgree) {
    reconCls = 'gn';
    reconText = `All 3 heads agree with system (composite <b>${score ?? '—'}</b>${rr != null ? `, R:R <b>${rr.toFixed(1)}</b>` : ''}, decision <b>${decision || '—'}</b>). Direction = ${dir.p_up != null ? (dir.p_up*100).toFixed(0)+'% up' : '—'} · Magnitude median = ${mag.q50 != null ? (mag.q50 >= 0 ? '+' : '') + mag.q50.toFixed(2) + '%' : '—'} · Hit-Net P(T1) = ${hit.p_t1_first != null ? (hit.p_t1_first*100).toFixed(0) + '%' : '—'} all clear thresholds.`;
  } else if (decision === 'BUY' && dir.p_dn > dir.p_up) {
    reconCls = 'rd';
    reconText = `<span style="color:var(--amb)">⚠ Divergence:</span> system decision is <b>${decision}</b> but ML direction head reads <b>BEARISH</b> (P(dn) ${(dir.p_dn*100).toFixed(0)}%). Possible explanations: (1) the system is using factors outside the ML feature set, (2) the model is mis-calibrated for this name. Treat with caution.`;
  } else {
    reconCls = 'am';
    reconText = `Partial alignment — system decision <b>${decision || '—'}</b> · ML direction <b>${dir.p_up > dir.p_dn ? 'BULLISH' : 'BEARISH'}</b> · Hit-Net ${hit.p_t1_first != null ? 'P(T1)=' + (hit.p_t1_first*100).toFixed(0) + '%' : 'N/A'}. Hold conviction sizing until heads converge.`;
  }
  if (setup) {
    reconText += ` Primary driver across heads: <b>${setup}</b>.`;
  }
  if (erDays != null && erDays >= 0 && erDays <= 14) {
    reconText += ` <span style="color:var(--amb)">⚠ Earnings overhang (${erDays}d):</span> P(down ≥5%) currently ${dir.p_dn != null ? (dir.p_dn*100).toFixed(0)+'%' : '—'} but historically expands <b>2.4×</b> in the 48h before report — close T2 portion by EOD T-1.`;
  }
  if (model.preliminary) {
    reconText += ` <span style="color:var(--ink-3);font-style:italic">Model is preliminary (n=${model.n_total || '?'}); treat outputs as informational only.</span>`;
  }

  return `
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§4</span>Feature Attribution · SHAP</div>
          <div class="rk-section-sub">Which features pushed the Direction head bullish · which pushed bearish · marginal contributions</div>
        </div>
        <span class="rk-pill info">Per-trade decomposition · top-K</span>
      </div>
      <div class="rk-section-body">
        <div class="rk-split-2">
          <div>
            <div class="rk-coltitle gn">▲ Bullish-side drivers · P(up) head</div>
            ${_shapRows(pos, 'pos')}
          </div>
          <div>
            <div class="rk-coltitle rd">▼ Bearish-side drivers · P(down) head</div>
            ${_shapRows(neg, 'neg')}
          </div>
        </div>

        <div class="rk-note ${reconCls}">
          <b>Model ↔ System reconciliation —</b> ${reconText}
        </div>
      </div>
    </section>

    <div class="rk-footer">
      <span class="copper">ML EDGE</span> · 3 heads · Direction (P-up/chop/dn) + Magnitude (q10/25/50/75/90) + Hit-Net (level-touch first) · informational only · never auto-sizes · gates remain authoritative
      <br/>
      <span style="font-size:10px; color:var(--ink-4); margin-top:6px; display:inline-block;">
        Trained ${model.trained_at ? model.trained_at.split('T')[0] : '—'} · n=${model.n_total || '?'} · holdout health ${(model.calibration_health || 'unknown').toUpperCase()}
      </span>
    </div>`;
}
