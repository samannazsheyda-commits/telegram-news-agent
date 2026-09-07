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

forceRefresh=async function(){
  if(refreshRunning)return;
  if(!requireConnection({type:'refresh'}))return;
  refreshRunning=true;
  const btn=$('refreshBtn'),old=btn.textContent;
  btn.disabled=true;btn.textContent='در حال بروزرسانی…';$('lastRefresh').textContent='در حال اسکن تازه ایجنت…';
  try{
    const id=await createCommand({action:'refresh',item_id:'',title:'',body:''});
    const result=await pollCommandResult(id,180000);
    if(result.status==='failed')throw Error(result.message||'اسکن ناموفق بود');
    if(result.status==='timeout')throw Error('اسکن طولانی شد؛ دوباره تلاش کن');
    await load(false);await loadSystem();
    toast(result.message||'بروزرسانی انجام شد');
  }catch(e){
    toast('بروزرسانی انجام نشد: '+e.message,15000);
  }finally{
    refreshRunning=false;btn.disabled=false;btn.textContent=old;
  }
};

// panel.js attached the old function directly, so replace the click handler too.
$('refreshBtn').onclick=forceRefresh;
