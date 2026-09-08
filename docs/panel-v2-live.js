(()=>{
  const RAW='https://raw.githubusercontent.com/samannazsheyda-commits/telegram-news-agent/main';
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const fmt=v=>{if(!v)return'—';const d=new Date(v);if(Number.isNaN(d.getTime()))return esc(v);return new Intl.DateTimeFormat('fa-IR',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'}).format(d)};
  const statusFa={new:'جدید',auto_published:'منتشرشده خودکار',waiting:'در انتظار',duplicate:'تکراری',rejected:'ردشده',failed:'خطا'};
  let rows=[];

  function activateLive(){
    const liveTab=document.querySelector('[data-view="live"]');
    const liveView=$('view-live');
    if(!liveTab||!liveView)return;
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===liveTab));
    document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v===liveView));
  }

  function pendingIsEmpty(){
    const pending=$('pendingCount');
    if(!pending)return true;
    const text=String(pending.textContent||'').replace(/[^0-9۰-۹]/g,'');
    const fa='۰۱۲۳۴۵۶۷۸۹';
    const en=text.replace(/[۰-۹]/g,d=>String(fa.indexOf(d)));
    return Number(en||0)===0;
  }

  function ensureUI(){
    const tabs=document.querySelector('.tabs');
    if(tabs&&!document.querySelector('[data-view="live"]')){
      const b=document.createElement('button');b.className='tab';b.dataset.view='live';b.textContent='ورودی زنده';tabs.prepend(b);
      b.addEventListener('click',activateLive);
    }
    if(!$('view-live')){
      const section=document.createElement('section');section.id='view-live';section.className='view';section.innerHTML='<div class="toolbar"><input id="liveSearch" class="field" type="search" placeholder="جست‌وجو در ورودی زنده"><select id="liveStatus" class="field"><option value="">همه وضعیت‌ها</option><option value="new">جدید</option><option value="auto_published">منتشرشده خودکار</option><option value="waiting">در انتظار</option><option value="duplicate">تکراری</option><option value="rejected">ردشده</option><option value="failed">خطا</option></select></div><div id="liveList" class="queue"><div class="skeleton"></div></div>';
      const pending=$('view-pending');pending?.parentNode?.insertBefore(section,pending);
      $('liveSearch')?.addEventListener('input',render);
      $('liveStatus')?.addEventListener('change',render);
    }
    if(!$('liveCount')){
      const stats=document.querySelector('.stats');
      const article=document.createElement('article');article.className='stat';article.innerHTML='<span>ورودی زنده</span><strong id="liveCount">۰</strong>';stats?.prepend(article);
    }
  }

  function render(){
    ensureUI();
    const q=($('liveSearch')?.value||'').trim().toLowerCase();
    const st=$('liveStatus')?.value||'';
    const filtered=rows.filter(r=>(!st||r.panel_status===st)&&(!q||`${r.title||''} ${r.source||''} ${r.decision_reason||''}`.toLowerCase().includes(q))).slice(0,120);
    $('liveCount').textContent=rows.length.toLocaleString('fa-IR');
    const list=$('liveList');if(!list)return;
    if(!filtered.length){list.innerHTML='<div class="empty">ورودی زنده‌ای برای این فیلتر نیست.</div>';return;}
    list.innerHTML=filtered.map(r=>`<article class="card"><strong style="font-family:var(--font-title);font-size:24px;line-height:1.8">${esc(r.title||'بدون تیتر')}</strong><div class="meta"><span class="badge">${esc(r.source||'منبع')}</span><span>${fmt(r.published_at_source||r.discovered_at)}</span><span>${esc(statusFa[r.panel_status]||r.panel_status||'—')}</span>${r.decision_reason?`<span class="reason">${esc(r.decision_reason)}</span>`:''}</div><div class="card-actions">${r.source_url?`<a class="btn ghost" href="${esc(r.source_url)}" target="_blank" rel="noopener">منبع</a>`:''}</div></article>`).join('');
  }

  async function loadLive(){
    ensureUI();
    try{
      const r=await fetch(`${RAW}/data/panel_live_feed.json?_=${Date.now()}`,{cache:'no-store'});
      if(!r.ok)throw new Error(`${r.status}`);
      const data=await r.json();rows=Array.isArray(data)?data:[];
      rows.sort((a,b)=>new Date(b.updated_at||b.discovered_at||0)-new Date(a.updated_at||a.discovered_at||0));
      render();
      if(rows.length&&pendingIsEmpty())activateLive();
    }catch(e){const list=$('liveList');if(list)list.innerHTML='<div class="empty">دریافت Live Feed ناموفق بود.</div>';}
  }

  document.addEventListener('DOMContentLoaded',()=>{ensureUI();loadLive();setInterval(loadLive,30000);});
})();
