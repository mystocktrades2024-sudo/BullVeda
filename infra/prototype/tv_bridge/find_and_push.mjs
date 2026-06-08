import CDP from 'chrome-remote-interface';
import fs from 'node:fs'; import path from 'node:path';
const HOST='localhost',PORT=9222;
const TICKER=(process.argv[2]||'NEM').toUpperCase();
const MODE=(process.argv[3]||'swing').toLowerCase();
const REPO='/Volumes/MyMacDisk/Claude Skills/SwingTrade';
const RES={swing:'1D',position:'1W',invest:'1M'}[MODE]||'1D';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const plan=JSON.parse(fs.readFileSync(path.join(REPO,'cache','target_engine',`${TICKER}_${MODE}.json`),'utf8'));
const api=`window.TradingViewApi._activeChartWidgetWV.value()`;

// find the chart target whose symbol contains TICKER
async function findTarget(){
  const list=(await (await fetch(`http://${HOST}:${PORT}/json/list`)).json())
    .filter(t=>t.type==='page'&&/tradingview\.com\/chart/i.test(t.url));
  for(const t of list){
    try{
      const c=await CDP({host:HOST,port:PORT,target:t.id});
      await c.Runtime.enable();
      const sym=(await c.Runtime.evaluate({expression:`(function(){try{return ${api}.symbol();}catch(e){return''}})()`,returnByValue:true})).result.value||'';
      await c.close();
      if(sym.toUpperCase().includes(TICKER)) return {id:t.id,sym};
    }catch(e){}
  }
  return null;
}
let tgt=null;
for(let i=0;i<20;i++){ tgt=await findTarget(); if(tgt){console.log('[found]',TICKER,'on',tgt.id.slice(0,8),'sym',tgt.sym);break;} await sleep(2000); }
if(!tgt){ console.error(`No chart showing ${TICKER}. Type ${TICKER} in your blank tab.`); process.exit(2); }

const c=await CDP({host:HOST,port:PORT,target:tgt.id});
await c.Runtime.enable(); await c.Page.enable();
const ev=async e=>(await c.Runtime.evaluate({expression:e,returnByValue:true,awaitPromise:true})).result.value;
await ev(`(function(){try{${api}.setResolution(${JSON.stringify(RES)},{});}catch(e){}})()`); await sleep(2000);
console.log('[chart]',await ev(`(function(){try{return ${api}.symbol()+' @ '+${api}.resolution();}catch(e){return'err'}})()`));

const t=Math.floor(Date.now()/1000);
const draw=async(price,color,label,dashed)=>{ if(price==null)return;
  const ov=JSON.stringify({linecolor:color,linewidth:2,linestyle:dashed?2:0,showLabel:true,text:label});
  await ev(`${api}.createShape({time:${t},price:${price}},{shape:'horizontal_line',overrides:${ov},text:${JSON.stringify(label)}})`);
  await sleep(250); console.log('[draw]',label);
};
await draw(plan.stop?.price,'#ef4444',`STOP ${plan.stop?.price} (${plan.stop?.distance_atr}xATR)`,true);
await draw(plan.entry?.price,'#f59e0b',`ENTRY ${plan.entry?.price}`,false);
await draw(plan.t1?.price,'#22c55e',`T1 ${plan.t1?.price} conf ${plan.t1?.confluence} R ${plan.t1?.r_multiple}`,false);
await draw(plan.t2?.price,'#22c55e',`T2 ${plan.t2?.price} conf ${plan.t2?.confluence}`,true);
await sleep(1500);
const shot=await c.Page.captureScreenshot({format:'png'});
const out=path.join(REPO,'infra','prototype','tv_bridge','shots'); fs.mkdirSync(out,{recursive:true});
const f=path.join(out,`${TICKER}_${MODE}_levels.png`); fs.writeFileSync(f,Buffer.from(shot.data,'base64'));
console.log('[shot]',f);
await c.close(); console.log('[done]');
