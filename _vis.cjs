const { chromium } = require('playwright');
(async () => {
  const auth='Basic '+Buffer.from('gari:Swing2026').toString('base64');
  const b=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const c=await b.newContext({viewport:{width:1400,height:1300},deviceScaleFactor:1.4,userAgent:'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',extraHTTPHeaders:{Authorization:auth}});
  const p=await c.newPage();
  await p.goto('http://localhost:7432/?t=ATEX&lens=smc',{waitUntil:'networkidle',timeout:60000});
  await p.waitForTimeout(2800);
  await p.evaluate(()=>{const x=document.querySelector('.smc-adv-toggle'); if(x) x.click();});
  await p.waitForTimeout(2500);
  for (let i=0;i<4;i++){ await p.evaluate(v=>{const bb=document.querySelector('.dpanel-body'); if(bb) bb.scrollTop=v;}, i*1250); await p.waitForTimeout(600); await p.screenshot({path:`/tmp/seg_${i}.png`, clip:{x:120,y:110,width:1280,height:1170}}); }
  await b.close();
})().catch(e=>{console.error(e.message);process.exit(1);});
