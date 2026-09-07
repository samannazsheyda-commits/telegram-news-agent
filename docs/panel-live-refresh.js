// Live-refresh hotfix: use GitHub Contents API after browser commands so the UI
// does not wait on raw.githubusercontent.com cache propagation.
async function readRepoJson(path){
  const headers=token()?authHeaders():{'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};
  const r=await fetch(`${API}/contents/${path}?ref=${BRANCH}&_=${Date.now()}`,{headers,cache:'no-store'});
  if(!r.ok)throw Error(await githubError(r));
  const payload=await r.json();
  const binary=atob(String(payload.content||'').replace(/\s/g,''));
  const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

// Pending news is a live queue, not an archive. Keep only items from today that
// are no older than two hours; editorial relevance/dedup remains handled separately.
todayQueueItem=function(r){
  const stamp=r.published_at_source||r.discovered_at||r.updated_at||'';
  if(!stamp)return false;
  const d=new Date(stamp);
  if(Number.isNaN(d.getTime()))return false;
  if(day(stamp)!==day(new Date().toISOString()))return false;
  return (Date.now()-d.getTime())<=2*60*60*1000;
};

pollCommandResult=async function(id,timeoutMs=90000){
  const started=Date.now();
  while(Date.now()-started<timeoutMs){
    try{
      const data=await readRepoJson(`panel_results/${id}.json`);
      if(TERMINAL_COMMAND.has(data.status))return data;
    }catch(e){
      if(!String(e.message||e).includes('GitHub 404')){
        // Ignore transient GitHub/API errors and keep polling; the button should
        // not get stuck just because one request failed.
      }
    }
    await new Promise(resolve=>setTimeout(resolve,1200));
  }
  return{command_id:id,status:'timeout',message:'نتیجه هنوز نهایی نشده است'};
};

load=async function(showLoading=true){
  try{
    if(showLoading&&queue.length===0)$('queueList').innerHTML='<div class="skeleton"></div><div class="skeleton"></div>';
    let q,h;
    try{
      [q,h]=await Promise.all([
        readRepoJson('data/editorial_queue.json'),
        readRepoJson('data/editorial_history.json')
      ]);
    }catch{
      [q,h]=await Promise.all([
        getJson(`${RAW}/data/editorial_queue.json`),
        getJson(`${RAW}/data/editorial_history.json`)
      ]);
    }
    queue=Array.isArray(q)?q:[];history=Array.isArray(h)?h:[];
    for(const id of [...hiddenItems]){if(!queue.some(x=>x.id===id&&x.status==='pending'))hiddenItems.delete(id)}
    populateFilters();applyFilters();renderHistoryViews();$('staleBadge').hidden=true;
    $('lastRefresh').textContent='آخرین دریافت پنل '+new Intl.DateTimeFormat('fa-IR',{timeStyle:'medium'}).format(new Date());
  }catch(e){$('staleBadge').hidden=false;toast('داده تازه دریافت نشد؛ نمایش قبلی حفظ شد')}
};

const AUTO_REFRESH_MS=5*60*1000;
let lastAutoRefreshAt=Date.now();

forceRefresh=async function(){
  if(refreshRunning)return false;
  if(!requireConnection({type:'refresh'}))return false;
  refreshRunning=true;
  const btn=$('refreshBtn'),old=btn.textContent;
  btn.disabled=true;btn.textContent='در حال بروزرسانی…';$('lastRefresh').textContent='در حال اسکن تازه ایجنت…';
  try{
    const id=await createCommand({action:'refresh',item_id:'',title:'',body:''});
    const result=await pollCommandResult(id,180000);
    if(result.status==='failed')throw Error(result.message||'اسکن ناموفق بود');
    if(result.status==='timeout')throw Error('اسکن طولانی شد؛ دوباره تلاش کن');
    await load(false);await loadSystem();
    const message=result.message||'بروزرسانی انجام شد';
    $('lastRefresh').textContent=message;
    toast(message,10000);
    return true;
  }catch(e){
    const message='بروزرسانی انجام نشد: '+e.message;
    $('lastRefresh').textContent=message;
    toast(message,15000);
    return false;
  }finally{
    lastAutoRefreshAt=Date.now();
    refreshRunning=false;btn.disabled=false;btn.textContent=old;
  }
};

async function autoRefreshIfDue(){
  if(document.visibilityState!=='visible')return;
  if(!token())return;
  if(refreshRunning)return;
  if(Date.now()-lastAutoRefreshAt<AUTO_REFRESH_MS)return;
  await forceRefresh();
}

// Check lightly and only launch a real scan once five minutes have elapsed.
// This avoids background-tab churn while keeping the visible newsroom current.
setInterval(autoRefreshIfDue,30000);
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='visible')autoRefreshIfDue();
});

// panel.js registered its original listener with addEventListener. An onclick
// assignment cannot replace that listener, so intercept in capture phase and
// make this API-backed refresh implementation the single authoritative handler.
const refreshButton=$('refreshBtn');
if(refreshButton){
  refreshButton.addEventListener('click',event=>{
    event.preventDefault();
    event.stopImmediatePropagation();
    forceRefresh();
  },true);
}
