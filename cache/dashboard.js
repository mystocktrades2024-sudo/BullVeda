
function mNavTo(tab,el){
  if(typeof showTab==='function')showTab(tab);
  document.querySelectorAll('.m-bnav-item').forEach(function(b){b.classList.remove('active')});
  el.classList.add('active');
  /* Close "more" drawer if open */
  var dr=document.getElementById('m-more-drawer');if(dr)dr.style.display='none';
}
function mNavShowMore(el){
  var dr=document.getElementById('m-more-drawer');
  if(!dr){
    dr=document.createElement('div');dr.id='m-more-drawer';
    dr.style.cssText='position:fixed;bottom:56px;left:0;right:0;z-index:8999;background:linear-gradient(180deg,#0a0f1a,#060a12);border-top:1px solid rgba(255,255,255,.08);padding:12px 16px;display:flex;flex-wrap:wrap;gap:8px;padding-bottom:env(safe-area-inset-bottom,8px)';
    var tabs=[['strategies','&#128640; Strategies'],['stocks-scanned','&#128269; Screener'],['themes','&#127760; Themes'],['research','&#128270; Research'],['leveraged','&#9889; Leveraged'],['industries','&#127981; Industries'],['market-intel','&#127758; Market'],['crypto','&#129689; Crypto'],['playbook','&#128218; Playbook'],['guide','&#128214; Guide'],['reference','&#128218; Reference'],['settings','&#9881;&#65039; Settings']];
    tabs.forEach(function(t){
      var b=document.createElement('button');
      b.innerHTML=t[1];
      b.style.cssText='padding:8px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.08);background:transparent;color:#94a3b8;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;min-height:40px;-webkit-tap-highlight-color:transparent';
      b.onclick=function(){mNavTo(t[0],el);dr.style.display='none';};
      dr.appendChild(b);
    });
    document.body.appendChild(dr);
  }else{
    dr.style.display=dr.style.display==='none'?'flex':'none';
  }
}
/* Hide bottom nav on desktop */
(function(){
  var nav=document.getElementById('m-bottom-nav');
  if(nav&&window.innerWidth>768)nav.style.display='none';
  window.addEventListener('resize',function(){
    if(nav)nav.style.display=window.innerWidth>768?'none':'';
  });
})();
