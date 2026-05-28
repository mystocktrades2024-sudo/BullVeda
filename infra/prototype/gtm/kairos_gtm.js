/* ════════════════════════════════════════════════════════════════
   Kairos GTM Prototype · theme engine + router + view renderers
   ════════════════════════════════════════════════════════════════ */

/* ── THEME ENGINE ── */
const THEMES = {
  "Obsidian Gold":{mode:'dark',bg:"#040404",panel:"rgba(22,19,12,.66)",panel2:"rgba(30,26,16,.6)",
    line:"rgba(201,162,74,.13)",line2:"rgba(201,162,74,.24)",line3:"rgba(201,162,74,.38)",
    ink:"#f7f2e7",ink2:"#bcb097",ink3:"#7d745e",ink4:"#4d4636",
    acc:"#d4a04a",accBr:"#f5d589",accDeep:"#9a7528",accg:"linear-gradient(135deg,#f5d589,#d4a04a 55%,#b8862f)",
    up:"#34e07e",upDeep:"#0f7a40",dn:"#ff5d6c",dnDeep:"#8a2530",warn:"#ffcb52",info:"#6ea8ff",uncert:"#5a5340",
    bgfx:"radial-gradient(1200px 700px at 85% -10%,rgba(201,162,74,.15),transparent 56%),radial-gradient(900px 700px at 0% 110%,rgba(201,162,74,.07),transparent 52%)",
    sw:["#f5d589","#34e07e","#040404"]},
  "Terminal Blue":{mode:'dark',bg:"#06080b",panel:"rgba(13,18,26,.7)",panel2:"rgba(18,24,36,.66)",
    line:"rgba(80,130,210,.13)",line2:"rgba(80,130,210,.24)",line3:"rgba(80,130,210,.4)",
    ink:"#dce3ee",ink2:"#8893a4",ink3:"#566173",ink4:"#3a4250",
    acc:"#2f81f7",accBr:"#5fa8ff",accDeep:"#1c4f9c",accg:"linear-gradient(135deg,#5fa8ff,#2f81f7 55%,#1c5fc0)",
    up:"#2ebd6b",upDeep:"#15703f",dn:"#e5484d",dnDeep:"#8a2a2e",warn:"#e0a93b",info:"#1fb8cd",uncert:"#4d545f",
    bgfx:"radial-gradient(1100px 650px at 82% -10%,rgba(47,129,247,.12),transparent 56%),radial-gradient(800px 600px at 0% 110%,rgba(31,184,205,.06),transparent 52%)",
    sw:["#2f81f7","#1fb8cd","#06080b"]},
  "Midnight Cyan":{mode:'dark',bg:"#06080d",panel:"rgba(18,24,38,.6)",panel2:"rgba(24,32,50,.6)",
    line:"rgba(120,160,220,.12)",line2:"rgba(120,160,220,.22)",line3:"rgba(120,160,220,.36)",
    ink:"#e8edf7",ink2:"#94a3c4",ink3:"#5b6982",ink4:"#3a4660",
    acc:"#5ce1e6",accBr:"#8af0f3",accDeep:"#1f8f93",accg:"linear-gradient(135deg,#8af0f3,#5ce1e6 55%,#2f9da0)",
    up:"#5bf2a0",upDeep:"#1c8a55",dn:"#ff6b81",dnDeep:"#8a2a38",warn:"#ffc24b",info:"#9d7bff",uncert:"#4d5666",
    bgfx:"radial-gradient(1100px 650px at 80% -10%,rgba(92,225,230,.12),transparent 58%),radial-gradient(800px 600px at 0% 110%,rgba(157,123,255,.07),transparent 55%)",
    sw:["#5ce1e6","#9d7bff","#06080d"]},
  "Deep Violet":{mode:'dark',bg:"#0b0717",panel:"rgba(30,18,54,.55)",panel2:"rgba(40,26,68,.55)",
    line:"rgba(180,140,255,.14)",line2:"rgba(180,140,255,.26)",line3:"rgba(180,140,255,.4)",
    ink:"#ece6fb",ink2:"#a99cce",ink3:"#6b5e92",ink4:"#473d68",
    acc:"#b48cff",accBr:"#d4b5ff",accDeep:"#6f4bc0",accg:"linear-gradient(135deg,#d4b5ff,#b48cff 55%,#8a5fe0)",
    up:"#67e8b0",upDeep:"#1f8a60",dn:"#ff6b9d",dnDeep:"#8a2a52",warn:"#ffc861",info:"#7bb6ff",uncert:"#5a4f7a",
    bgfx:"radial-gradient(1100px 650px at 80% -10%,rgba(180,140,255,.16),transparent 58%),radial-gradient(800px 600px at 0% 110%,rgba(255,110,199,.09),transparent 55%)",
    sw:["#b48cff","#ff6ec7","#0b0717"]},
  "Forest Terminal":{mode:'dark',bg:"#04110c",panel:"rgba(10,32,22,.55)",panel2:"rgba(14,42,30,.55)",
    line:"rgba(110,230,160,.13)",line2:"rgba(110,230,160,.24)",line3:"rgba(110,230,160,.38)",
    ink:"#e2f5ea",ink2:"#8db8a2",ink3:"#54776a",ink4:"#3a5448",
    acc:"#3ddc84",accBr:"#7dff9f",accDeep:"#1c8a4f",accg:"linear-gradient(135deg,#7dff9f,#3ddc84 55%,#1f9a5a)",
    up:"#3ddc84",upDeep:"#157a45",dn:"#ff7a6b",dnDeep:"#8a3025",warn:"#ffd24b",info:"#5fd0ff",uncert:"#4a6356",
    bgfx:"radial-gradient(1000px 600px at 80% -10%,rgba(61,220,132,.12),transparent 60%)",
    sw:["#3ddc84","#7dff9f","#04110c"]},
  "Bronze Noir":{mode:'dark',bg:"#0c0a08",panel:"rgba(28,22,16,.6)",panel2:"rgba(38,30,22,.6)",
    line:"rgba(217,119,87,.14)",line2:"rgba(217,119,87,.26)",line3:"rgba(217,119,87,.4)",
    ink:"#efe6da",ink2:"#b3a48f",ink3:"#7a6b56",ink4:"#544636",
    acc:"#d97757",accBr:"#e8a878",accDeep:"#a04e32",accg:"linear-gradient(135deg,#e8a878,#d97757 55%,#b35636)",
    up:"#7fb069",upDeep:"#4a7a3a",dn:"#d6604f",dnDeep:"#8a3328",warn:"#e0a458",info:"#6ea8c4",uncert:"#5a4d3c",
    bgfx:"radial-gradient(1000px 600px at 80% -10%,rgba(217,119,87,.12),transparent 58%)",
    sw:["#d97757","#7fb069","#0c0a08"]},
  "Arctic Light":{mode:'light',bg:"#f4f6fa",panel:"rgba(255,255,255,.82)",panel2:"rgba(244,247,252,.92)",
    line:"rgba(30,50,80,.10)",line2:"rgba(30,50,80,.16)",line3:"rgba(30,50,80,.28)",
    ink:"#16202e",ink2:"#566273",ink3:"#94a0b0",ink4:"#c2cbd6",
    acc:"#2563eb",accBr:"#1d4ed8",accDeep:"#1e40af",accg:"linear-gradient(135deg,#3b82f6,#2563eb 55%,#1d4ed8)",
    up:"#16a34a",upDeep:"#15803d",dn:"#dc2626",dnDeep:"#b91c1c",warn:"#d97706",info:"#0891b2",uncert:"#94a0b0",
    bgfx:"radial-gradient(1100px 650px at 80% -10%,rgba(37,99,235,.06),transparent 58%)",
    sw:["#2563eb","#16a34a","#f4f6fa"]},
};
const TKEYS={bg:'--bg',panel:'--panel',panel2:'--panel2',line:'--line',line2:'--line2',line3:'--line3',
  ink:'--ink',ink2:'--ink2',ink3:'--ink3',ink4:'--ink4',acc:'--acc',accBr:'--acc-br',accDeep:'--acc-deep',
  accg:'--accg',up:'--up',upDeep:'--up-deep',dn:'--dn',dnDeep:'--dn-deep',warn:'--warn',info:'--info',uncert:'--uncert',bgfx:'--bgfx'};
function applyTheme(name){
  const t=THEMES[name];if(!t)return;const r=document.documentElement.style;
  Object.entries(TKEYS).forEach(([k,v])=>r.setProperty(v,t[k]));
  document.getElementById('themename').textContent=name;
  document.getElementById('themesw').innerHTML=t.sw.map(c=>`<i style="background:${c}"></i>`).join('');
  document.querySelectorAll('.themeopt').forEach(o=>o.classList.toggle('on',o.dataset.n===name));
  try{localStorage.setItem('kairos-gtm-theme',name);}catch(e){}
  // redraw charts that depend on CSS vars
  if(window._redraw)window._redraw();
}
function buildThemeMenu(){
  const m=document.getElementById('thememenu');
  m.innerHTML=Object.entries(THEMES).map(([n,t])=>
    `<div class="themeopt" data-n="${n}"><span class="sw">${t.sw.map(c=>`<i style="background:${c}"></i>`).join('')}</span>${n}</div>`).join('');
  m.querySelectorAll('.themeopt').forEach(o=>o.onclick=e=>{e.stopPropagation();applyTheme(o.dataset.n);m.classList.remove('open');});
}
document.getElementById('themebtn').onclick=e=>{e.stopPropagation();document.getElementById('thememenu').classList.toggle('open');};
document.addEventListener('click',()=>document.getElementById('thememenu').classList.remove('open'));

/* ── SAMPLE DATA ── */
const PICKS=[
 {v:'BUY',tier:'T1',sym:'IONQ',setup:'Breakout Expansion',score:93,t:31,f:28,s:30,n:24,px:63.62,chg:6.1,d20:42,sp:[18,17,18,13,11,12,7,5,2],entry:'61.89–64.77',stop:56.12,t1:84.96,t2:99.38,eq:'fresh',rr:3.6,rs:100,rvol:1.8,cat:'T1',wr:'62',lb:'44',nn:'41',sec:'Technology'},
 {v:'BUY',tier:'T1',sym:'COMM',setup:'Breakout Expansion',score:90,t:30,f:30,s:24,n:28,px:19.58,chg:6.1,d20:31,sp:[16,17,13,14,10,9,10,6,4],entry:'19.38–19.71',stop:17.05,t1:27.03,t2:32.02,eq:'fresh',rr:3.1,rs:91,rvol:2.1,cat:'T1',wr:'58',lb:'41',nn:'63',sec:'Technology'},
 {v:'BUY',tier:'T2',sym:'CORZ',setup:'Breakout Expansion',score:88,t:28,f:18,s:30,n:30,px:26.37,chg:4.2,d20:38,sp:[19,17,18,14,15,10,9,6,4],entry:'25.85–26.72',stop:21.65,t1:40.19,t2:49.46,eq:'fresh',rr:3.0,rs:100,rvol:1.6,cat:'T1',wr:'',lb:'',nn:'7',thin:1,sec:'Technology'},
 {v:'BUY',tier:'T2',sym:'APLD',setup:'Breakout Expansion',score:85,t:28,f:22,s:18,n:24,px:45.14,chg:3.4,d20:24,sp:[14,16,12,13,14,9,11,7,6],entry:'43.80–46.04',stop:39.32,t1:61.72,t2:72.92,eq:'fresh',rr:3.0,rs:100,rvol:2.4,cat:'T1',wr:'55',lb:'38',nn:'28',sec:'Technology'},
 {v:'WATCH',tier:'T3',sym:'CRNC',setup:'Breakout Expansion',score:86,t:22,f:14,s:30,n:20,px:11.34,chg:-1.2,d20:52,sp:[15,13,14,11,12,10,11,12,13],entry:'11.08–11.52',stop:10.20,t1:14.60,t2:16.80,eq:'ext',rr:3.7,rs:100,rvol:1.1,cat:'T2',wr:'',lb:'',nn:'4',thin:1,sec:'Technology'},
 {v:'WATCH',tier:'T2',sym:'GLXY',setup:'Breakout Expansion',score:64,t:18,f:14,s:18,n:14,px:29.62,chg:2.1,d20:18,sp:[12,13,11,12,10,11,9,10,8],entry:'28.99–30.04',stop:19.59,t1:59.29,t2:79.14,eq:'pull',rr:4.0,rs:99,rvol:1.3,cat:'T2',wr:'53',lb:'36',nn:'22',sec:'Financials'},
 {v:'WATCH',tier:'T3',sym:'COHU',setup:'Trend Continuation',score:66,t:18,f:16,s:18,n:14,px:49.93,chg:1.6,d20:16,sp:[14,13,12,13,11,12,10,9,8],entry:'49.08–50.5',stop:41.27,t1:75.35,t2:92.39,eq:'pull',rr:3.4,rs:100,rvol:1.4,cat:'T2',wr:'56',lb:'39',nn:'33',sec:'Technology'},
 {v:'WATCH',tier:'T3',sym:'FIVN',setup:'Trend Continuation',score:62,t:17,f:14,s:16,n:15,px:22.79,chg:0.9,d20:9,sp:[11,12,10,11,12,10,9,8,9],entry:'22.29–23.13',stop:19.66,t1:31.86,t2:37.96,eq:'pull',rr:3.2,rs:94,rvol:1.0,cat:'T3',wr:'49',lb:'33',nn:'31',sec:'Technology'},
 {v:'WATCH',tier:'T3',sym:'BRZE',setup:'Trend Continuation',score:61,t:15,f:16,s:16,n:14,px:25.45,chg:0.7,d20:7,sp:[12,11,12,11,10,11,10,10,9],entry:'24.97–25.77',stop:24.06,t1:29.30,t2:31.92,eq:'valid',rr:3.0,rs:100,rvol:0.8,cat:'T3',wr:'54',lb:'37',nn:'26',sec:'Technology'},
 {v:'WATCH',tier:'T3',sym:'BEN',setup:'Trend Continuation',score:60,t:15,f:14,s:16,n:15,px:31.67,chg:0.3,d20:3,sp:[11,11,10,11,10,10,9,10,9],entry:'31.44–31.82',stop:30.46,t1:35.14,t2:37.48,eq:'valid',rr:3.0,rs:72,rvol:0.7,cat:'T3',wr:'50',lb:'34',nn:'44',sec:'Financials'},
 {v:'AVOID',tier:'—',sym:'WST',setup:'Trend Continuation',score:54,t:14,f:18,s:10,n:12,px:316.17,chg:-1.1,d20:-4,sp:[11,12,11,10,11,12,11,12,13],entry:'—',stop:298,t1:366,t2:400,eq:'miss',rr:3.0,rs:94,rvol:0.4,cat:'T2',wr:'47',lb:'31',nn:'38',sec:'Healthcare'},
 {v:'AVOID',tier:'—',sym:'MNRO',setup:'Breakdown',score:38,t:8,f:10,s:8,n:12,px:24.10,chg:-4.2,d20:-12,sp:[14,13,14,12,13,11,12,13,14],entry:'—',stop:25,t1:20,t2:18,eq:'miss',rr:2.1,rs:34,rvol:1.9,cat:'T3',wr:'42',lb:'28',nn:'29',sec:'Consumer Cyc'},
];
let _sel='IONQ';
const byS=s=>PICKS.find(p=>p.sym===s)||PICKS[0];

/* ── HELPERS ── */
function cssv(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim();}
function ringSvg(score,size){const sz=size||36,r=sz/2-3,circ=2*Math.PI*r;
  const c=score>=80?'var(--up)':score>=72?'var(--acc-br)':score>=50?'var(--ink2)':'var(--ink3)';
  const off=circ*(1-score/100);
  return `<span style="position:relative;display:inline-block;width:${sz}px;height:${sz}px;vertical-align:middle">
    <svg width="${sz}" height="${sz}" style="transform:rotate(-90deg)">
    <circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="color-mix(in srgb,var(--acc) 12%,transparent)" stroke-width="3"/>
    <circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="${c}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}" style="filter:drop-shadow(0 0 4px ${c})"/></svg>
    <span class="ringn" style="color:${c};font-size:${sz>40?'15px':'12px'}">${score}</span></span>`;}
function sparkPts(d,w,h){const lo=Math.min(...d),hi=Math.max(...d),rg=(hi-lo)||1;
  return d.map((y,i)=>`${(i/(d.length-1)*w).toFixed(1)},${(h-((y-lo)/rg)*h).toFixed(1)}`).join(' ');}
function tfsn(t,f,s,n){const seg=(v,mx)=>{const r=v/mx,c=r>=.75?'var(--up)':r>=.5?'var(--warn)':'var(--dn)';
  return `<b style="width:7px;height:15px;display:inline-block;border-radius:2px;background:${c};opacity:${(.4+.6*r).toFixed(2)}"></b>`;};
  return `<span style="display:inline-flex;gap:2px;vertical-align:middle">${seg(t,35)}${seg(f,30)}${seg(s,30)}${seg(n,25)}</span>`;}

/* candlestick chart */
function genBars(n){const bars=[];let px=46;for(let i=0;i<n;i++){const bo=i>n*0.78;let o=px,c;
  if(!bo){c=42+Math.sin(i/4)*4+(Math.random()-0.5)*1.6;}else{c=o+0.6+Math.random()*1.5;}
  const h=Math.max(o,c)+Math.random()*1.1,l=Math.min(o,c)-Math.random()*1.1;bars.push({o,h,l,c});px=c;}
  bars[n-1]={o:61.2,h:64.1,l:60.85,c:63.62};return bars;}
function drawCandles(svg,withZones){
  if(!svg)return;const W=svg.clientWidth||640,H=svg.clientHeight||280;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const n=60,bars=genBars(n),hi=(withZones?86:66),lo=38,padR=44,padT=8,volH=withZones?44:28,chartH=H-volH-padT-4;
  const x=i=>(i/(n-1))*(W-padR),y=p=>padT+((hi-p)/(hi-lo))*chartH,bw=Math.max(2,(W-padR)/n*0.6);
  function ema(per){let k=2/(per+1),e=bars[0].c,o=[];bars.forEach(b=>{e=b.c*k+e*(1-k);o.push(e);});return o;}
  const e8=ema(8),e21=ema(21);let s='';
  const ticks=withZones?[40,50,56.12,61.89,64.77,70,80,84.96]:[40,50,60,64];
  ticks.forEach(t=>{if(t<lo||t>hi)return;const yy=y(t).toFixed(1);let c='color-mix(in srgb,var(--acc) 8%,transparent)',lab='var(--ink3)',d='';
    if(t===56.12){c='color-mix(in srgb,var(--dn) 50%,transparent)';lab='var(--dn)';d='4 3';}
    if(t===61.89||t===64.77){c='color-mix(in srgb,var(--acc) 45%,transparent)';lab='var(--acc-br)';d='3 3';}
    if(t===84.96){c='color-mix(in srgb,var(--up) 50%,transparent)';lab='var(--up)';d='4 3';}
    s+=`<line x1="0" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="${c}" stroke-width="1" ${d?`stroke-dasharray="${d}"`:''}/>`;
    s+=`<text x="${W-padR+4}" y="${(+yy+3)}" fill="${lab}" font-family="JetBrains Mono" font-size="9" font-weight="600">${t.toFixed(t%1?2:0)}</text>`;});
  if(withZones)s+=`<rect x="0" y="${y(64.77)}" width="${W-padR}" height="${y(61.89)-y(64.77)}" fill="color-mix(in srgb,var(--acc) 7%,transparent)"/>`;
  const volY0=padT+chartH+volH;
  bars.forEach((b,i)=>{const vv=(i>46?1+Math.random()*0.6:0.4+Math.random()*0.5),vh=(vv/1.6)*volH,up=b.c>=b.o;
    s+=`<rect x="${(x(i)-bw/2).toFixed(1)}" y="${(volY0-vh).toFixed(1)}" width="${bw.toFixed(1)}" height="${vh.toFixed(1)}" fill="${up?'color-mix(in srgb,var(--up) 35%,transparent)':'color-mix(in srgb,var(--dn) 35%,transparent)'}"/>`;});
  bars.forEach((b,i)=>{const up=b.c>=b.o,c=up?'var(--up)':'var(--dn)',cx=x(i);
    s+=`<line x1="${cx.toFixed(1)}" y1="${y(b.h).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(b.l).toFixed(1)}" stroke="${c}" stroke-width="1"/>`;
    const yo=y(b.o),yc=y(b.c),top=Math.min(yo,yc),hg=Math.max(1.5,Math.abs(yc-yo));
    s+=`<rect x="${(cx-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${hg.toFixed(1)}" fill="${c}"/>`;});
  const el=(a,col)=>`<polyline points="${a.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="${col}" stroke-width="1.3" opacity=".85"/>`;
  s+=el(e8,'var(--acc-br)')+el(e21,'var(--info)');
  svg.innerHTML=s;
}

/* ════════ VIEW RENDERERS ════════ */
const V={};

/* DECK */
V.deck=()=>{
  const top=byS('IONQ');
  const stats=[{v:'7',l:'BUY Signals',d:'+2 vs yest',cls:'up',spk:[10,9,11,8,7,6,4,3]},
    {v:'93',l:'Top Score · IONQ',d:'p99 universe',cls:'gold',spk:[6,7,5,8,6,9,10,12]},
    {v:'3.2R',l:'Avg Reward',d:'≥3:1 gate',cls:'',spk:[8,7,9,8,10,9,11,10]},
    {v:'58%',l:'Win Rate · LB 41',d:'n=132 choppy',cls:'',spk:[7,8,7,9,8,9,10,9]},
    {v:'1.84',l:'Profit Factor',d:'30-day',cls:'up',spk:[6,7,8,7,9,10,11,12]}];
  const picks=PICKS.filter(p=>p.v==='BUY'||p.sym==='CRNC').slice(0,4);
  return `
  <div class="hero">
    <div class="card chartcard"><div class="glow" style="width:240px;height:240px;top:-80px;right:-50px"></div>
      <div class="chc-top"><div class="chc-id"><div><span class="sym">IONQ</span><span class="badge">▲ TOP CONVICTION</span></div>
        <div class="name">IonQ Inc · Technology · Breakout Expansion · RS 100</div></div>
        <div class="chc-px"><div class="p">$63.62</div><div class="c">▲ +$3.66 +6.10%</div></div></div>
      <div class="tf"><span>1D</span><span>1W</span><span class="on">3M</span><span>6M</span><span>1Y</span></div>
      <div class="chartbox"><svg id="deckchart" preserveAspectRatio="none"></svg></div>
    </div>
    <div class="card deccard"><div class="glow" style="width:180px;height:180px;background:var(--up);bottom:-60px;left:-40px;opacity:.2"></div>
      <div class="dec-top">${ringSvg(93,90)}<div class="dec-v"><div class="v">BUY</div><div class="conf">High conviction · Tier 1</div><div class="g">cleared <b>11/11</b> gates</div></div></div>
      <div class="riskg">
        <div class="rc danger"><div class="l">Max loss/sh</div><div class="v dn">−$7.50</div><div class="d">stop −11.8%</div></div>
        <div class="rc"><div class="l">Size ½-Kelly</div><div class="v gold">6.2%</div><div class="d">regime adj</div></div>
        <div class="rc"><div class="l">Target 1</div><div class="v up">$84.96</div><div class="d">+33.5% 3.6R</div></div>
        <div class="rc"><div class="l">Target 2</div><div class="v up">$99.38</div><div class="d">+56.2% 5.5R</div></div>
      </div>
      <div class="btnrow"><button class="btn buy">BUY · Limit 63.20</button><button class="btn gh" onclick="go('detail')">Detail →</button></div>
    </div>
  </div>
  <div class="grid4" style="margin-bottom:14px">${stats.map(s=>{
    const pts=sparkPts(s.spk,84,30);
    return `<div class="stat"><div class="v ${s.cls}">${s.v}</div><div class="l">${s.l}</div><div class="d" style="${s.cls==='up'?'color:var(--up)':''}">${s.d}</div>
      <svg class="spk" viewBox="0 0 84 30"><polyline points="${pts}" fill="none" stroke="${s.cls==='up'?'var(--up)':'var(--acc)'}" stroke-width="2" stroke-linecap="round"/></svg></div>`;}).join('')}</div>
  <div class="secti"><h2>Today's Conviction</h2><span class="rule"></span><span class="more" onclick="go('scanner')">View scanner →</span></div>
  <div class="grid4">${picks.map(p=>{const col=p.chg>=0?'var(--up)':'var(--dn)';const pts=sparkPts(p.sp,260,56);
    return `<div class="pcard" onclick="openDetail('${p.sym}')">
      <div class="pc-top"><div class="pc-l"><div class="sym">${p.sym}</div><div class="meta">${p.tier} · ${p.sec}</div></div><span class="vpill ${p.v.toLowerCase()}">${p.v}</span></div>
      <svg class="pc-chart" viewBox="0 0 260 56" preserveAspectRatio="none"><defs><linearGradient id="g${p.sym}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".26"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
        <polygon points="0,56 ${pts} 260,56" fill="url(#g${p.sym})"/><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div class="pc-bot"><div><span class="pc-px">$${p.px.toFixed(2)}</span> <span class="pc-chg ${p.chg>=0?'up':'dn'}">${p.chg>=0?'+':''}${p.chg}%</span></div>
        <div style="display:flex;align-items:center;gap:7px">${ringSvg(p.score,34)}<span class="pc-rr">${p.rr}R</span></div></div>
    </div>`;}).join('')}</div>`;
};

/* SCANNER */
V.scanner=()=>{
  const rows=PICKS.map((p,i)=>{const scC=p.score>=80?'var(--up)':p.score>=72?'var(--acc-br)':p.score>=50?'var(--ink)':'var(--ink3)';
    const spC=p.d20>=20?'var(--up)':p.d20>=0?'var(--acc)':'var(--dn)';
    return `<tr class="${p.v==='AVOID'?'dim':''} ${p.sym===_sel?'sel':''}" onclick="openDetail('${p.sym}')">
      <td class="l" style="color:var(--ink4);font:700 10px var(--mono)">${String(i+1).padStart(2,'0')}</td>
      <td class="l"><span class="vpill ${p.v.toLowerCase()}">${p.v}</span></td>
      <td class="l"><span style="font:700 9px var(--mono);color:${p.tier==='T1'?'var(--acc-br)':'var(--ink3)'}">${p.tier}</span></td>
      <td class="l"><span class="sym2">${p.sym}</span></td>
      <td class="l"><span style="font:500 11px var(--sans);color:var(--ink2)">${p.setup}</span></td>
      <td><span style="display:inline-flex;align-items:center;gap:8px;justify-content:flex-end">${ringSvg(p.score,34)}</span></td>
      <td class="l">${tfsn(p.t,p.f,p.s,p.n)}</td>
      <td><span style="font:700 12px var(--mono)">${p.px.toFixed(2)}</span></td>
      <td><span style="display:inline-flex;align-items:center;gap:7px;justify-content:flex-end"><span style="font:700 12px var(--mono);color:${p.chg>=0?'var(--up)':'var(--dn)'}">${p.chg>=0?'+':''}${p.chg}%</span>
        <svg width="70" height="20" viewBox="0 0 150 22"><polyline points="${sparkPts(p.sp,150,22)}" fill="none" stroke="${spC}" stroke-width="2" stroke-linecap="round"/></svg></span></td>
      <td class="l"><span style="font:600 11px var(--mono);color:var(--ink2)">${p.entry}</span></td>
      <td class="l"><span class="eq ${p.eq}">${p.eq.toUpperCase()}</span></td>
      <td><span style="font:800 12px var(--mono);color:${p.rr>=3?'var(--up)':'var(--ink2)'}">${p.rr.toFixed(1)}</span></td>
      <td><span class="rsb"><span class="b"><i style="width:${p.rs}%"></i></span><span class="n">${p.rs}</span></span></td>
      <td><span style="font:700 11px var(--mono);color:${p.rvol>=1.5?'var(--up)':'var(--ink2)'}">${p.rvol.toFixed(1)}×</span></td>
      <td><span class="wrc ${p.thin?'thin':''}">${p.thin?`<span class="lb">n${p.nn}·thin</span>`:`<b>${p.wr}%</b> <span class="lb">LB${p.lb}·n${p.nn}</span>`}</span></td>
      <td class="l"><span style="font:500 10px var(--mono);color:var(--ink3)">${p.sec}</span></td>
    </tr>`;}).join('');
  return `
  <div class="fbar">
    <div class="funnel"><b>1,847</b><span class="arr">scanned →</span><b>488</b><span class="arr">scored →</span><b>74</b><span class="arr">gates →</span><span class="fin"><b>7</b> BUY</span></div>
    <span class="vchip on">ALL · 488</span><span class="vchip buy">BUY · 7</span><span class="vchip">WATCH · 67</span><span class="vchip">AVOID · 112</span>
    <span class="qf on">Fresh</span><span class="qf">≥3:1</span><span class="qf">Tier 1</span>
    <div class="search"><span>⌕</span><input placeholder="ticker…"></div>
  </div>
  <div class="scanwrap">
    <div class="card" style="margin:0"><div style="overflow:auto;max-height:calc(100vh - 240px)"><table class="tbl">
      <thead><tr><th class="l">#</th><th class="l">V</th><th class="l">TIER</th><th class="l">SYM</th><th class="l">SETUP</th><th class="on">SCORE</th><th class="l">T·F·S·N</th><th>PX</th><th>Δ%·20D</th><th class="l">ENTRY</th><th class="l">QUAL</th><th>R:R</th><th>RS</th><th>RVOL</th><th>WR·n</th><th class="l">SECTOR</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>
    <div>
      <div class="rcard"><div class="rcard-h">⛲ Selection Funnel</div>
        <div style="padding-bottom:14px">
        <div class="fstep"><span class="fl">Scanned</span><span class="fbar2"><i style="width:100%"></i></span><span class="fn">1847</span></div>
        <div class="fstep"><span class="fl">Liquidity</span><span class="fbar2"><i style="width:71%"></i></span><span class="fn">1312</span></div>
        <div class="fstep"><span class="fl">Scored</span><span class="fbar2"><i style="width:26%"></i></span><span class="fn">488</span></div>
        <div class="fstep"><span class="fl">Gates ✓</span><span class="fbar2"><i style="width:8%"></i></span><span class="fn">74</span></div>
        <div class="fstep final"><span class="fl">BUY</span><span class="fbar2"><i style="width:3%"></i></span><span class="fn">7</span></div></div></div>
      <div class="rcard"><div class="rcard-h">📊 Score Distribution<span class="n">488</span></div>
        <div class="histo"><div class="hb" style="height:18%"></div><div class="hb" style="height:34%"></div><div class="hb" style="height:58%"></div><div class="hb" style="height:82%"></div><div class="hb" style="height:100%"></div><div class="hb" style="height:71%"></div><div class="hb th" style="height:44%"></div><div class="hb buy" style="height:26%"></div><div class="hb buy" style="height:14%"></div><div class="hb buy" style="height:7%"></div></div>
        <div class="histo-x"><span>20</span><span>40</span><span>60</span><span>72▲</span><span>80</span><span>100</span></div>
        <div style="padding:0 16px 14px;font:500 10.5px var(--sans);color:var(--ink3);font-style:italic">Gold = BUY floor <b style="color:var(--acc-br);font-style:normal">72</b>. Only the right tail clears it — 7 of 488.</div></div>
    </div>
  </div>`;
};

/* CONVICTION 9-cell */
V.conviction=()=>{
  const cv=PICKS.filter(p=>p.score>=60).slice(0,9);
  return `<div class="secti"><h2>Conviction Grid</h2><span class="rule"></span><span class="more">regime-gated · 9 cells</span></div>
  <div class="grid9">${cv.map(p=>{
    const fc=[['var(--up)',p.t/35],['var(--acc)',p.f/20*100/100],['var(--info)',p.s/30],['var(--warn)',p.n/25]];
    return `<div class="cvcell" onclick="openDetail('${p.sym}')">
      <div class="top"><div><div class="sym">${p.sym}</div><div class="sub">${p.setup} · ${p.sec}</div></div>${ringSvg(p.score,52)}</div>
      <div style="display:flex;gap:7px;margin-top:11px"><span class="vpill ${p.v.toLowerCase()}">${p.v}</span><span class="tierb">${p.tier}</span><span class="chip">R:R <b style="color:var(--up)">${p.rr}</b></span></div>
      <div class="factors">${[p.t/35,p.f/20,p.s/30,p.n/25].map((r,i)=>`<b style="background:${['var(--up)','var(--acc)','var(--info)','var(--warn)'][i]};opacity:${(.3+.7*r).toFixed(2)}"></b>`).join('')}</div>
      <div class="narr">RS ${p.rs} · ${p.eq.toUpperCase()} entry · ${p.thin?`<span style="color:var(--uncert)">n${p.nn} thin sample</span>`:`WR ${p.wr}% (LB ${p.lb}, n${p.nn})`}</div>
    </div>`;}).join('')}</div>`;
};

/* PERFORMANCE */
V.performance=()=>{
  return `<div class="verdict-banner"><div class="big">EDGE: POSITIVE</div><div class="txt">System is <b>profitable</b> over 132 trades · PF <b>1.84</b> · Win rate <b>58%</b> (Wilson LB 41%). Edge concentrates in <b>trending</b> regimes; choppy is acceptable.</div></div>
  <div class="grid4" style="margin-bottom:14px">
    <div class="stat"><div class="v up">+18.4%</div><div class="l">Return · 30d</div><div class="d">vs SPY +5.0%</div></div>
    <div class="stat"><div class="v">1.84</div><div class="l">Profit Factor</div><div class="d">gross win/loss</div></div>
    <div class="stat"><div class="v">2.19</div><div class="l">Sharpe · 126d</div><div class="d">robust &gt;1.5</div></div>
    <div class="stat"><div class="v dn" style="color:var(--dn)">−4.2%</div><div class="l">Max Drawdown</div><div class="d">recovered</div></div>
  </div>
  <div class="grid2">
    <div class="card"><div class="card-h">🏆 Setup Family Podium <span class="n">Wilson CI</span></div><div class="card-b"><div class="podium">
      <div class="pod"><div class="medal">🥇</div><div class="nm">Squeeze Exp</div><div class="wr">71%</div><div class="ci">LB 52% · n28</div></div>
      <div class="pod"><div class="medal">🥈</div><div class="nm">52wk Breakout</div><div class="wr">64%</div><div class="ci">LB 48% · n41</div></div>
      <div class="pod"><div class="medal">🥉</div><div class="nm">EMA21 Pullback</div><div class="wr">58%</div><div class="ci">LB 44% · n63</div></div>
    </div></div></div>
    <div class="card"><div class="card-h">🎯 Score Calibration</div><div class="card-b"><div class="calib">
      <div class="calib-row"><span class="cl">90+</span><span class="ct"><span class="pred" style="width:72%"></span><span class="act" style="left:69%"></span></span><span style="font:700 11px var(--mono);color:var(--up);text-align:right">69%</span></div>
      <div class="calib-row"><span class="cl">80–89</span><span class="ct"><span class="pred" style="width:62%"></span><span class="act" style="left:60%"></span></span><span style="font:700 11px var(--mono);text-align:right">60%</span></div>
      <div class="calib-row"><span class="cl">70–79</span><span class="ct"><span class="pred" style="width:54%"></span><span class="act" style="left:55%"></span></span><span style="font:700 11px var(--mono);text-align:right">55%</span></div>
      <div class="calib-row"><span class="cl">60–69</span><span class="ct"><span class="pred" style="width:48%"></span><span class="act" style="left:46%"></span></span><span style="font:700 11px var(--mono);text-align:right">46%</span></div>
      <div class="note" style="margin-top:8px">Bar = predicted WR · line = actual. Well-calibrated: higher scores → higher realized win rate.</div>
    </div></div></div>
  </div>`;
};

/* PORTFOLIO */
V.portfolio=()=>{
  return `<div class="pf-tiles">
    <div class="pf-tile"><div class="l">Equity</div><div class="v">$98,108</div><div class="d">start $100,000</div></div>
    <div class="pf-tile"><div class="l">Open P&L</div><div class="v up">+$1,240</div><div class="d">3 positions</div></div>
    <div class="pf-tile"><div class="l">Net Beta</div><div class="v">1.12</div><div class="d">long-tilted</div></div>
    <div class="pf-tile"><div class="l">Cash</div><div class="v">42%</div><div class="d">choppy regime</div></div>
  </div>
  <div class="card"><div class="card-h">💼 Open Positions</div><div style="overflow:auto"><table class="tbl">
    <thead><tr><th class="l">SYM</th><th>ENTRY</th><th>LAST</th><th>%CHG</th><th>STOP</th><th>T1</th><th>→T1</th><th>→STOP</th><th>HELD</th><th>SIZE</th></tr></thead>
    <tbody>
      <tr onclick="openDetail('IONQ')"><td class="l"><span class="sym2">IONQ</span></td><td>61.20</td><td>63.62</td><td style="color:var(--up)">+3.95%</td><td style="color:var(--dn)">56.12</td><td style="color:var(--up)">84.96</td><td>33.5%</td><td>11.8%</td><td>2d</td><td>6.2%</td></tr>
      <tr onclick="openDetail('CORZ')"><td class="l"><span class="sym2">CORZ</span></td><td>25.10</td><td>26.37</td><td style="color:var(--up)">+5.06%</td><td style="color:var(--dn)">21.65</td><td style="color:var(--up)">40.19</td><td>52.4%</td><td>17.9%</td><td>4d</td><td>4.1%</td></tr>
      <tr onclick="openDetail('COMM')"><td class="l"><span class="sym2">COMM</span></td><td>18.90</td><td>19.58</td><td style="color:var(--up)">+3.60%</td><td style="color:var(--dn)">17.05</td><td style="color:var(--up)">27.03</td><td>38.0%</td><td>12.9%</td><td>1d</td><td>3.4%</td></tr>
    </tbody></table></div></div>
  <div class="grid2">
    <div class="card"><div class="card-h">🗺 Sector Exposure</div><div class="card-b"><table class="kv">
      <tr><td class="k">Technology</td><td class="v gold">82%</td></tr><tr><td class="k">Financials</td><td class="v">12%</td></tr><tr><td class="k">Cash</td><td class="v">42% (unallocated)</td></tr></table>
      <div class="note" style="margin-top:8px">⚠ High Tech concentration — correlated cluster. Size new Tech adds fractionally.</div></div></div>
    <div class="card"><div class="card-h">📓 Closed Journal · last 7d</div><div class="card-b"><table class="kv">
      <tr><td class="k">NVDA · 52wk Breakout</td><td class="v up">+$420 · 2.1R</td></tr><tr><td class="k">SHLS · Trend Cont.</td><td class="v up">+$185 · 1.4R</td></tr><tr><td class="k">ZM · Trend Cont.</td><td class="v dn">−$210 · −1.0R</td></tr></table></div></div>
  </div>`;
};

/* OPTIONS */
V.options=()=>{
  const rows=PICKS.filter(p=>p.v!=='AVOID').slice(0,7).map(p=>{
    const st=p.score>=88?'STRONG':p.score>=75?'SOLID':'BUILDING';const stc=st==='STRONG'?'var(--up)':st==='SOLID'?'var(--warn)':'var(--ink2)';
    const pcr=(0.08+Math.random()*0.4).toFixed(2);
    return `<tr onclick="openDetail('${p.sym}')"><td class="l"><span class="sym2">${p.sym}</span></td>
      <td>${p.px.toFixed(2)}</td><td><span style="color:${stc};font:700 10px var(--mono)">${st}</span></td>
      <td style="color:${pcr<0.3?'var(--up)':'var(--ink2)'}">${pcr}</td><td>$${(p.px*1.1).toFixed(0)}C</td><td>${(12+Math.floor(Math.random()*20))}d</td>
      <td style="color:var(--up)">$${(0.5+Math.random()*2).toFixed(1)}M</td><td>${(40+Math.floor(Math.random()*30))}%</td><td>±${(8+Math.random()*8).toFixed(1)}%</td></tr>`;}).join('');
  return `<div class="secti"><h2>Options Flow</h2><span class="rule"></span><span class="more">UOA imbalance · vol regime</span></div>
  <div class="grid4" style="margin-bottom:14px">
    <div class="stat"><div class="v up">0.41</div><div class="l">Mkt Put/Call</div><div class="d">greed</div></div>
    <div class="stat"><div class="v">16.9</div><div class="l">VIX</div><div class="d">VIX3M 19.9 contango</div></div>
    <div class="stat"><div class="v gold">+8.1</div><div class="l">Avg VRP</div><div class="d">IV − HV20</div></div>
    <div class="stat"><div class="v">$27M</div><div class="l">Top Call Premium</div><div class="d">APLD</div></div>
  </div>
  <div class="card"><div class="card-h">🐋 Unusual Options Activity</div><div style="overflow:auto"><table class="tbl">
    <thead><tr><th class="l">SYM</th><th>PX</th><th>STATUS</th><th>P/C</th><th>ATM K</th><th>DTE</th><th>PREMIUM</th><th>ATM IV</th><th>IMPLIED MOVE</th></tr></thead>
    <tbody>${rows}</tbody></table></div></div>`;
};

/* DETAIL */
const DTABS=[['overview','Overview'],['plan','Plan · Ticket'],['chart','Chart'],['technicals','Technicals'],['fundamentals','Fundamentals'],['intel','Intelligence'],['options','Options'],['track','Track Record']];
let _dtab='overview';
V.detail=()=>{
  const p=byS(_sel);
  const chips=`<span class="chip">Setup <b>${p.setup}</b></span><span class="chip">Entry <b>${p.eq.toUpperCase()}</b></span><span class="chip">RS <b>${p.rs}</b></span><span class="chip">Cat <b>${p.cat}</b></span><span class="chip">R:R <b style="color:var(--up)">${p.rr}</b></span>`;
  return `
  <div class="card" style="margin-bottom:14px"><div class="glow" style="width:220px;height:220px;top:-90px;right:180px"></div>
    <div style="display:flex;align-items:center;gap:22px;padding:20px 24px">
      <div><div style="display:flex;align-items:center;gap:11px"><span style="font:800 32px var(--sans)">${p.sym}</span><span class="vpill ${p.v.toLowerCase()}">${p.v}</span><span class="tierb">${p.tier}</span></div>
        <div style="font:500 12px var(--sans);color:var(--ink3);margin-top:5px">${p.sym} · ${p.sec} · ${p.setup}</div>
        <div style="margin-top:10px">${chips}</div></div>
      <div style="margin-left:auto;text-align:right"><div style="font:800 34px var(--mono)">$${p.px.toFixed(2)}</div><div style="font:700 15px var(--mono);color:${p.chg>=0?'var(--up)':'var(--dn)'};margin-top:2px">${p.chg>=0?'▲ +':'▼ '}${p.chg}%</div></div>
      <div style="display:flex;flex-direction:column;align-items:center;gap:3px">${ringSvg(p.score,90)}<span style="font:700 8px var(--mono);letter-spacing:.14em;color:var(--ink3);text-transform:uppercase">Score</span></div>
    </div>
  </div>
  <div class="subnav" id="subnav">${DTABS.map(([id,lb])=>`<button data-t="${id}" class="${id===_dtab?'on':''}" onclick="setDtab('${id}')">${lb}</button>`).join('')}</div>
  <div id="dcontent">${dPane(p)}</div>`;
};
function dPane(p){
  if(_dtab==='overview')return `
    <div class="grid2"><div class="card"><div class="card-h">⚡ Thesis · why BUY</div>
      <div class="card-b"><div class="thesis"><b>${p.sym} — ${p.setup}, ${p.eq} entry.</b> RS pinned at <em>${p.rs}</em>; mechanism is supply absorption before expansion. Cleared all gates at a <em>${p.rr}:1</em> reward profile.</div>
      <div class="grid4" style="margin-top:14px">
        <div class="rc danger"><div class="l">Stop</div><div class="v dn">$${p.stop}</div><div class="d">1.25× ATR</div></div>
        <div class="rc"><div class="l">Entry</div><div class="v gold" style="font-size:14px">${p.entry}</div><div class="d">${p.eq}</div></div>
        <div class="rc"><div class="l">T1</div><div class="v up">$${p.t1}</div><div class="d">${p.rr}R</div></div>
        <div class="rc"><div class="l">T2</div><div class="v up">$${p.t2}</div></div>
      </div></div></div>
      <div class="card"><div class="card-h">📈 Price · 60d</div><div class="chartbox" style="height:220px;padding:8px 12px"><svg id="ovchart" preserveAspectRatio="none"></svg></div></div></div>
    <div class="card"><div class="card-h">🔍 Read-through</div><div class="card-b" style="padding-top:4px">
      <span class="sw-chip pos"><b>RSI 64</b><span class="r">rising, not overbought</span></span>
      <span class="sw-chip pos"><b>RVOL ${p.rvol}×</b><span class="r">accumulation</span></span>
      <span class="sw-chip pos"><b>EMA stack</b><span class="r">8&gt;21&gt;50</span></span>
      <span class="sw-chip neu"><b>IV 41%ile</b><span class="r">not rich</span></span>
      <span class="sw-chip neg"><b>Earn +18d</b><span class="r">monitor</span></span></div></div>
    <div class="card"><div class="card-h">🛑 Pre-mortem · what kills it</div><div class="card-b"><ul class="falsify">
      <li><b>Close below $${p.stop}</b> — base breaks, thesis void. Hard stop.</li>
      <li><b>RVOL &lt; 1.0 on breakout</b> — no demand behind move.</li>
      <li><b>Sector rolls −3%+</b> — high-beta correlated cluster.</li></ul>
      <div style="margin-top:6px"><span class="gate">liquidity</span><span class="gate">earnings blackout</span><span class="gate">regime</span><span class="gate">entry quality</span><span class="gate">R:R ≥ 3:1</span><span class="gate">RS ≥ 75</span><span class="gate">Sharpe gate</span></div></div></div>`;
  if(_dtab==='plan')return `<div class="grid3">
    <div class="card"><div class="card-h" style="color:var(--dn)">① Risk first</div><div class="card-b"><table class="kv">
      <tr><td class="k">Max loss/sh</td><td class="v dn">−$7.50</td></tr><tr><td class="k">Stop (close)</td><td class="v dn">$${p.stop}</td></tr><tr><td class="k">Portfolio risk</td><td class="v">0.74%</td></tr></table></div></div>
    <div class="card"><div class="card-h">② Size</div><div class="card-b"><table class="kv">
      <tr><td class="k">Method</td><td class="v">½-Kelly</td></tr><tr><td class="k">Base size</td><td class="v gold">6.2%</td></tr><tr><td class="k">Shares</td><td class="v">158</td></tr></table></div></div>
    <div class="card"><div class="card-h">③ Targets</div><div class="card-b"><table class="kv">
      <tr><td class="k">Entry</td><td class="v gold">${p.entry}</td></tr><tr><td class="k">T1</td><td class="v up">$${p.t1} · ${p.rr}R</td></tr><tr><td class="k">T2</td><td class="v up">$${p.t2}</td></tr><tr><td class="k">Hold</td><td class="v">7–21d</td></tr></table></div></div></div>`;
  if(_dtab==='chart')return `<div class="card"><div class="card-h">📈 ${p.sym} · candles + volume + EMA</div><div class="chartbox" style="height:340px;padding:8px 12px"><svg id="bigchart" preserveAspectRatio="none"></svg></div></div>`;
  if(_dtab==='technicals')return `<div class="grid2">
    <div class="card"><div class="card-h">🧱 5-Pillar · vs cohort</div><div class="card-b">
      ${[['Technicals','EMA·RVOL·MACD',p.t,35,89,55,24],['Catalyst','R:R·UOA·IV',p.f,20,85,50,26],['RS+Sector','63d',p.s,30,100,68,25],['Smart Money','insider',p.n,15,60,42,30],['Quality','fundamentals',7,10,70,48,30]].map(([nm,sub,v,mx,fill,bl,bw])=>
      `<div class="pillar"><div class="ph"><span class="pn">${nm} <small>${sub}</small></span><span class="pv">${v}<span class="mx">/${mx}</span></span></div><div class="track"><div class="band" style="left:${bl}%;width:${bw}%"></div><i style="width:${fill}%"></i></div></div>`).join('')}
      <div class="note" style="margin-top:8px">Dashed band = 7-candidate cohort. ${p.sym} leads on RS &amp; technicals.</div></div></div>
    <div class="card"><div class="card-h">📐 Indicators</div><div class="card-b"><table class="kv">
      <tr><td class="k">EMA 8/21/50</td><td class="v gold">stacked ✓</td></tr><tr><td class="k">RSI(14)</td><td class="v">64 rising</td></tr><tr><td class="k">MACD</td><td class="v up">+1.84 cross</td></tr><tr><td class="k">ADX</td><td class="v">31 trending</td></tr><tr><td class="k">RVOL</td><td class="v up">${p.rvol}×</td></tr><tr><td class="k">SMC</td><td class="v gold">BOS bullish · HH</td></tr></table></div></div></div>`;
  if(_dtab==='fundamentals')return `<div class="grid3">
    <div class="card"><div class="card-h">💰 Valuation</div><div class="card-b"><table class="kv"><tr><td class="k">Mkt cap</td><td class="v">$2.1B</td></tr><tr><td class="k">P/S fwd</td><td class="v">24.3×</td></tr><tr><td class="k">Analyst PT</td><td class="v gold">+24%</td></tr></table></div></div>
    <div class="card"><div class="card-h">📊 Growth</div><div class="card-b"><table class="kv"><tr><td class="k">Rev YoY</td><td class="v up">+95%</td></tr><tr><td class="k">Gross margin</td><td class="v">58%</td></tr><tr><td class="k">EPS</td><td class="v dn">−$0.18</td></tr></table></div></div>
    <div class="card"><div class="card-h">🏦 Balance</div><div class="card-b"><table class="kv"><tr><td class="k">Cash</td><td class="v gold">$382M</td></tr><tr><td class="k">Debt</td><td class="v">$12M</td></tr><tr><td class="k">Inst own</td><td class="v">61%</td></tr></table></div></div></div>`;
  if(_dtab==='intel')return `<div class="grid2">
    <div class="card"><div class="card-h">📰 News</div><div class="card-b" style="padding-top:4px"><span class="sw-chip pos" style="display:block;margin-bottom:8px"><b>+0.82</b><span class="r">New qubit architecture; PT +24% — Bloomberg</span></span><span class="sw-chip pos" style="display:block"><b>+0.61</b><span class="r">Quantum names rally on contracts — Reuters</span></span></div></div>
    <div class="card"><div class="card-h">🐋 Options · UOA</div><div class="card-b"><table class="kv"><tr><td class="k">Status</td><td class="v gold">STRONG</td></tr><tr><td class="k">Put/Call</td><td class="v up">0.12</td></tr><tr><td class="k">Call premium</td><td class="v gold">$894k</td></tr><tr><td class="k">Whale</td><td class="v">$70C +18d</td></tr></table></div></div></div>`;
  if(_dtab==='options')return `<div class="grid3">
    <div class="card"><div class="card-h">📊 Vol structure</div><div class="card-b"><table class="kv"><tr><td class="k">ATM IV</td><td class="v">52%</td></tr><tr><td class="k">IV %ile</td><td class="v">41%</td></tr><tr><td class="k">VRP</td><td class="v up">+8.1</td></tr><tr><td class="k">25Δ skew</td><td class="v">call rich</td></tr></table></div></div>
    <div class="card"><div class="card-h">🎯 Key strikes</div><div class="card-b"><table class="kv"><tr><td class="k">Max pain</td><td class="v">$60</td></tr><tr><td class="k">Max OI</td><td class="v gold">$70C</td></tr><tr><td class="k">Implied move</td><td class="v">±11.4%</td></tr></table></div></div>
    <div class="card"><div class="card-h">💡 Suggested</div><div class="card-b"><table class="kv"><tr><td class="k">Structure</td><td class="v gold">Bull call spread</td></tr><tr><td class="k">Legs</td><td class="v">+65C/−85C</td></tr><tr><td class="k">Max gain</td><td class="v up">+228%</td></tr></table></div></div></div>`;
  if(_dtab==='track')return `<div class="grid2">
    <div class="card"><div class="card-h">📐 ${p.setup} × regime <span class="n">Wilson CI</span></div><div class="card-b">
      <div class="ci-row"><span class="ci-name">All regimes</span><span class="ci"><span class="ax"></span><span class="be" style="left:45%"></span><span class="band" style="left:44%;width:30%"></span><span class="pt" style="left:58%"></span></span><span class="ci-v"><b>58%</b> <span class="n">n=132</span></span></div>
      <div class="ci-row"><span class="ci-name">Risk-On Choppy</span><span class="ci"><span class="ax"></span><span class="be" style="left:45%"></span><span class="band" style="left:41%;width:28%"></span><span class="pt" style="left:55%"></span></span><span class="ci-v"><b>55%</b> <span class="n">n=63</span></span></div>
      <div class="ci-row"><span class="ci-name">Trending</span><span class="ci"><span class="ax"></span><span class="be" style="left:45%"></span><span class="band" style="left:52%;width:26%"></span><span class="pt" style="left:67%"></span></span><span class="ci-v"><b>67%</b> <span class="n">n=41</span></span></div>
      <div class="ci-row"><span class="ci-name">Panic</span><span class="ci thin"><span class="ax"></span><span class="be" style="left:45%"></span><span class="band" style="left:18%;width:62%"></span><span class="pt" style="left:40%"></span></span><span class="ci-v thin"><b>40%</b> <span class="n">n=5</span></span></div>
      <div class="note" style="margin-top:8px">Wider band = less certain. Panic (n=5) too thin — greyed. Edge concentrates in <b>trending</b>.</div></div></div>
    <div class="card"><div class="card-h">📈 Forward 5d · distribution</div><div class="card-b">
      <div style="height:130px"><svg viewBox="0 0 320 130" preserveAspectRatio="none" style="width:100%;height:100%">
        <line x1="0" y1="84" x2="320" y2="84" stroke="color-mix(in srgb,var(--acc) 20%,transparent)" stroke-width="1"/>
        <path d="M 4 84 L 316 28 L 316 116 Z" fill="color-mix(in srgb,var(--up) 8%,transparent)"/><path d="M 4 84 L 316 46 L 316 98 Z" fill="color-mix(in srgb,var(--up) 16%,transparent)"/>
        <line x1="4" y1="84" x2="316" y2="66" stroke="var(--up)" stroke-width="2"/><circle cx="316" cy="66" r="3.5" fill="var(--up)"/></svg></div>
      <table class="kv" style="margin-top:6px"><tr><td class="k">q10/q50/q90</td><td class="v"><span class="dn">−3.6%</span> / <b class="gold">+0.3%</b> / <span class="up">+3.1%</span></td></tr><tr><td class="k">P(T1 first)</td><td class="v">41%</td></tr></table></div></div></div>`;
  return '';
}
window.setDtab=id=>{_dtab=id;document.querySelectorAll('#subnav button').forEach(b=>b.classList.toggle('on',b.dataset.t===id));
  document.getElementById('dcontent').innerHTML=dPane(byS(_sel));afterRender();};
window.openDetail=sym=>{_sel=sym;_dtab='overview';go('detail');};

/* ── ROUTER ── */
const TABS=[['deck','Command Deck'],['scanner','Signal Scanner'],['conviction','Conviction'],['detail','Detail'],['options','Options Flow'],['portfolio','Portfolio'],['performance','Performance']];
let _view='deck';
function go(v){_view=v;render();}
window.go=go;
function render(){
  document.getElementById('tabs').innerHTML=TABS.map(([id,lb])=>`<button class="${id===_view?'on':''}" onclick="go('${id}')">${lb}</button>`).join('');
  document.getElementById('views').innerHTML=`<div class="view on">${(V[_view]||V.deck)()}</div>`;
  afterRender();
}
function afterRender(){
  if(document.getElementById('deckchart'))drawCandles(document.getElementById('deckchart'),true);
  if(document.getElementById('ovchart'))drawCandles(document.getElementById('ovchart'),false);
  if(document.getElementById('bigchart'))drawCandles(document.getElementById('bigchart'),true);
}
window._redraw=afterRender;

/* ── INIT ── */
buildThemeMenu();
let _t='Obsidian Gold';try{_t=localStorage.getItem('kairos-gtm-theme')||_t;}catch(e){}
applyTheme(_t);
render();
