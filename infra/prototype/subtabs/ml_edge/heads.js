// subtabs/ml_edge/heads.js — §1 "3-Head Decomposition" section.
//
// Replaces the prior buildHeadsRow + buildHeadCards pair. Emits one section with
// 3 chart cards side-by-side: Direction (3-class bars), Magnitude (q-fan box), Hit-Net
// (stacked outcome bars). Each card pulls from payload + model meta.

const fmtSgn = (v, d=2) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
const fmtPct = (v, d=0) => v == null ? '—' : (Number(v) * 100).toFixed(d) + '%';

export function buildHeads(ctx) {
  const { payload, meta, model } = ctx;
  const dir = payload.direction || {};
  const mag = payload.magnitude || {};
  const hit = payload.hit_net || {};
  const dirM = model.direction || {};
  const magM = model.magnitude || {};
  const hitM = model.hit_net || {};

  // Direction bar values (px) — 3 bars proportional
  const pUp   = dir.p_up != null ? dir.p_up : 0;
  const pChop = dir.p_chop != null ? dir.p_chop : 0;
  const pDn   = dir.p_dn != null ? dir.p_dn : 0;
  // x-axis: 0..100% mapped to height
  const barTop = (p) => 140 - p * 110;  // 0% → y=140, 100% → y=30

  // Magnitude box-whisker scaling: y axis −10% to +10% mapped to 30..150
  const yForMag = (pct) => {
    const clamped = Math.max(-10, Math.min(10, pct));
    return 90 - clamped * 6; // 0 → 90 (center), +10 → 30, −10 → 150
  };
  const q10 = mag.q10, q25 = mag.q25, q50 = mag.q50, q75 = mag.q75, q90 = mag.q90;

  // Hit-Net stacked bars
  const pT1 = hit.p_t1_first;
  const pT2 = hit.p_t2_first;
  const pStop = hit.p_stop_first != null ? hit.p_stop_first : (pT1 != null ? 1 - pT1 : null);
  const pRange = hit.p_range != null ? hit.p_range : 0.18; // fallback

  // Model status pills
  const dirStatus = dirM.accuracy >= 0.55 ? 'pass' : dirM.accuracy >= 0.40 ? 'warn' : 'info';
  const magStatus = magM.pinball_loss_by_q && parseFloat(magM.pinball_loss_by_q['0.5']) < 2.5 ? 'pass' : 'warn';
  const hitStatus = hitM.auc >= 0.65 ? 'pass' : hitM.auc >= 0.55 ? 'warn' : 'info';
  const statusText = { pass: 'CONFIRMED', warn: 'CAUTIONED', info: 'PRELIM' };

  return `
    <section class="rk-section">
      <div class="rk-section-head">
        <div>
          <div class="rk-section-title"><span class="num">§1</span>3-Head Decomposition</div>
          <div class="rk-section-sub">How Direction · Magnitude · Hit-Net independently see the 5d forward</div>
        </div>
        <span class="rk-pill info">${meta.model_version || 'v4.0'} · LGBM + QUANTILE + HIT${model.trained_at ? ` · retrained ${model.trained_at.split('T')[0]}` : ''}</span>
      </div>
      <div class="rk-section-body">
        <div class="rk-split-3">

          <!-- DIRECTION card -->
          <div class="rk-chart-card dir">
            <div class="rk-chart-title">
              ▲ DIRECTION · 3-class P(up / chop / down)
              <span class="legend"><i style="background:var(--gn)"></i>UP <i style="background:var(--ink-3)"></i>chop <i style="background:var(--rd)"></i>DN</span>
            </div>
            <svg viewBox="0 0 320 170" style="width:100%; height:160px;">
              <line class="axis" x1="40" y1="140" x2="300" y2="140"/>
              <line class="grid" x1="40" y1="30"  x2="300" y2="30"/>
              <line class="grid" x1="40" y1="70"  x2="300" y2="70"/>
              <line class="grid" x1="40" y1="105" x2="300" y2="105"/>

              <text class="lbl" x="36" y="140" text-anchor="end">0</text>
              <text class="lbl" x="36" y="105" text-anchor="end">25%</text>
              <text class="lbl" x="36" y="70"  text-anchor="end">50%</text>
              <text class="lbl" x="36" y="30"  text-anchor="end">100%</text>

              <!-- UP bar -->
              <rect x="70"  y="${barTop(pUp)}"   width="60" height="${140 - barTop(pUp)}"   fill="var(--gn)"/>
              <text class="vlbl" x="100" y="${barTop(pUp) - 6}"   text-anchor="middle" fill="var(--gn)">${fmtPct(pUp)}</text>
              <text class="lbl"  x="100" y="156" text-anchor="middle">UP ≥ 5%</text>

              <!-- CHOP bar -->
              <rect x="155" y="${barTop(pChop)}" width="60" height="${140 - barTop(pChop)}" fill="var(--ink-3)"/>
              <text class="vlbl" x="185" y="${barTop(pChop) - 6}" text-anchor="middle">${fmtPct(pChop)}</text>
              <text class="lbl"  x="185" y="156" text-anchor="middle">chop</text>

              <!-- DN bar -->
              <rect x="240" y="${barTop(pDn)}"   width="60" height="${140 - barTop(pDn)}"   fill="var(--rd)"/>
              <text class="vlbl" x="270" y="${barTop(pDn) - 6}"   text-anchor="middle" fill="var(--rd)">${fmtPct(pDn)}</text>
              <text class="lbl"  x="270" y="156" text-anchor="middle">DN ≥ 5%</text>
            </svg>
            <div class="rk-note ${dirStatus === 'pass' ? 'gn' : 'am'}" style="margin-top:6px; padding:6px 10px; font-size:11px;">
              <b>GBM 3-class</b> · ${dirM.n_holdout || '?'} holdout · ACC <b>${dirM.accuracy != null ? (dirM.accuracy*100).toFixed(0)+'%' : '—'}</b> · ${statusText[dirStatus]}.
              ${dirM.log_loss != null ? `Log loss <b>${dirM.log_loss.toFixed(2)}</b>.` : ''}
            </div>
          </div>

          <!-- MAGNITUDE card -->
          <div class="rk-chart-card mag">
            <div class="rk-chart-title">
              μ MAGNITUDE · Quantile fan (q10/25/50/75/90)
              <span class="legend"><i style="background:var(--violet)"></i>median <i style="background:rgba(167,139,250,0.20)"></i>IQR</span>
            </div>
            <svg viewBox="0 0 320 170" style="width:100%; height:160px;">
              <line class="axis" x1="40" y1="90" x2="300" y2="90"/>
              <line class="grid" x1="40" y1="30"  x2="300" y2="30"/>
              <line class="grid" x1="40" y1="55"  x2="300" y2="55"/>
              <line class="grid" x1="40" y1="125" x2="300" y2="125"/>
              <line class="grid" x1="40" y1="150" x2="300" y2="150"/>

              <text class="lbl" x="36" y="30"  text-anchor="end">+10%</text>
              <text class="lbl" x="36" y="55"  text-anchor="end">+5%</text>
              <text class="lbl" x="36" y="90"  text-anchor="end">0%</text>
              <text class="lbl" x="36" y="125" text-anchor="end">−5%</text>
              <text class="lbl" x="36" y="150" text-anchor="end">−10%</text>

              <line x1="40" y1="90" x2="300" y2="90" stroke="var(--ink-3)" stroke-width="0.5" stroke-dasharray="2,2"/>

              ${q10 != null && q90 != null ? `
                <!-- Whisker line (q10 to q90) -->
                <line x1="170" y1="${yForMag(q90)}" x2="170" y2="${yForMag(q10)}" stroke="var(--violet)" stroke-width="1.2"/>
                <!-- Caps -->
                <line x1="160" y1="${yForMag(q90)}" x2="180" y2="${yForMag(q90)}" stroke="var(--violet)" stroke-width="1.5"/>
                <line x1="160" y1="${yForMag(q10)}" x2="180" y2="${yForMag(q10)}" stroke="var(--violet)" stroke-width="1.5"/>
              ` : ''}

              ${q25 != null && q75 != null ? `
                <!-- IQR box (q25 to q75) -->
                <rect x="130" y="${yForMag(q75)}" width="80" height="${yForMag(q25) - yForMag(q75)}" fill="var(--violet)" opacity="0.22"/>
                <rect x="130" y="${yForMag(q75)}" width="80" height="${yForMag(q25) - yForMag(q75)}" fill="none" stroke="var(--violet)" stroke-width="1"/>
              ` : ''}

              ${q50 != null ? `
                <!-- Median (q50) -->
                <line x1="130" y1="${yForMag(q50)}" x2="210" y2="${yForMag(q50)}" stroke="var(--violet)" stroke-width="2.5"/>
              ` : ''}

              <!-- Labels (right side) -->
              ${q90 != null ? `<text class="vlbl" x="215" y="${yForMag(q90) + 4}" fill="var(--violet)">q90 ${fmtSgn(q90)}</text>` : ''}
              ${q75 != null ? `<text class="vlbl" x="215" y="${yForMag(q75) + 4}" fill="var(--ink-3)">q75 ${fmtSgn(q75)}</text>` : ''}
              ${q50 != null ? `<text class="vlbl" x="215" y="${yForMag(q50) + 4}" fill="var(--violet)">q50 ${fmtSgn(q50)}</text>` : ''}
              ${q25 != null ? `<text class="vlbl" x="215" y="${yForMag(q25) + 4}" fill="var(--ink-3)">q25 ${fmtSgn(q25)}</text>` : ''}
              ${q10 != null ? `<text class="vlbl" x="215" y="${yForMag(q10) + 4}" fill="var(--violet)">q10 ${fmtSgn(q10)}</text>` : ''}

              <text class="lbl" x="46" y="166">5d horizon · σ-conditioned</text>
            </svg>
            <div class="rk-note" style="margin-top:6px; padding:6px 10px; font-size:11px; border-left-color:var(--violet)">
              <b>Quantile GBM</b> · 5 heads at α ∈ {0.10, 0.25, 0.50, 0.75, 0.90}.
              ${magM.pinball_loss_by_q && magM.pinball_loss_by_q['0.5'] ? `Pinball q50 <b>${parseFloat(magM.pinball_loss_by_q['0.5']).toFixed(2)}</b>.` : ''}
              ${mag.skew != null && Math.abs(mag.skew) > 0.2 ? `Skew <b>${mag.skew >= 0 ? '+' : ''}${mag.skew.toFixed(2)}</b> → ${mag.skew > 0 ? 'up-skewed' : 'down-skewed'}.` : ''}
            </div>
          </div>

          <!-- HIT-NET card -->
          <div class="rk-chart-card hit">
            <div class="rk-chart-title">
              ◎ HIT-NET · Touch-first competing risks
              <span class="legend"><i style="background:var(--gn)"></i>T1/T2 first <i style="background:var(--rd)"></i>stop first</span>
            </div>
            <svg viewBox="0 0 320 170" style="width:100%; height:160px;">
              <text class="lbl" x="40" y="32">Hit T1 before stop</text>
              <rect x="40" y="38" width="240" height="14" fill="var(--bg-3)"/>
              ${pT1 != null ? `<rect x="40" y="38" width="${pT1 * 240}" height="14" fill="var(--gn)"/>` : ''}
              <text class="vlbl" x="290" y="50" text-anchor="end" fill="var(--gn)">${pT1 != null ? (pT1*100).toFixed(0)+'%' : '—'}</text>

              <text class="lbl" x="40" y="68">Hit T2 before stop</text>
              <rect x="40" y="74" width="240" height="14" fill="var(--bg-3)"/>
              ${pT2 != null ? `<rect x="40" y="74" width="${pT2 * 240}" height="14" fill="var(--gn)" opacity="0.7"/>` : ''}
              <text class="vlbl" x="290" y="86" text-anchor="end" fill="var(--gn)">${pT2 != null ? (pT2*100).toFixed(0)+'%' : '—'}</text>

              <text class="lbl" x="40" y="104">Hit stop before T1</text>
              <rect x="40" y="110" width="240" height="14" fill="var(--bg-3)"/>
              ${pStop != null ? `<rect x="40" y="110" width="${pStop * 240}" height="14" fill="var(--rd)"/>` : ''}
              <text class="vlbl" x="290" y="122" text-anchor="end" fill="var(--rd)">${pStop != null ? (pStop*100).toFixed(0)+'%' : '—'}</text>

              <text class="lbl" x="40" y="140">Range-bound 5d</text>
              <rect x="40" y="146" width="240" height="14" fill="var(--bg-3)"/>
              <rect x="40" y="146" width="${pRange * 240}" height="14" fill="var(--ink-3)"/>
              <text class="vlbl" x="290" y="158" text-anchor="end" fill="var(--ink-2)">${(pRange*100).toFixed(0)}%</text>
            </svg>
            <div class="rk-note ${hitStatus === 'pass' ? 'gn' : 'am'}" style="margin-top:6px; padding:6px 10px; font-size:11px;">
              <b>GBM binary</b> · ${hitM.n_holdout || '?'} holdout · AUC <b>${hitM.auc != null ? hitM.auc.toFixed(2) : '—'}</b> · Brier <b>${hitM.brier != null ? hitM.brier.toFixed(3) : '—'}</b>.
              Output drops into Kelly sizing via P(T1 first) > 0.60 threshold.
            </div>
          </div>

        </div>
      </div>
    </section>`;
}
