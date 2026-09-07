(()=>{
'use strict';

function nowFa(){
  return new Intl.DateTimeFormat('fa-IR',{timeStyle:'medium'}).format(new Date());
}

async function authoritativeRefresh(){
  if(refreshRunning)return;
  if(!requireConnection({type:'refresh'}))return;
  refreshRunning=true;
  const btn=$('refreshBtn');
  const old=btn?.textContent||'اسکن فوری';
  if(btn){btn.disabled=true;btn.textContent='در حال بروزرسانی…'}
  if($('lastRefresh'))$('lastRefresh').textContent='در حال اسکن واقعی منابع…';
  try{
    const id=await createCommand({action:'refresh',item_id:'',title:'',body:''});
    const result=await pollCommandResult(id,180000);
    if(result.status==='failed')throw Error(result.message||'اسکن ناموفق بود');
    if(result.status==='timeout')throw Error('اسکن طولانی شد و هنوز پاسخ نهایی نرسیده است');
    await load(false);
    await loadSystem();
    const message=result.message||'بروزرسانی انجام شد';
    if($('lastRefresh'))$('lastRefresh').textContent=`نتیجه اسکن: ${message} — ${nowFa()}`;
    toast(message,12000);
  }catch(e){
    const message='بروزرسانی انجام نشد: '+(e?.message||e);
    if($('lastRefresh'))$('lastRefresh').textContent=`نتیجه اسکن: ${message} — ${nowFa()}`;
    toast(message,15000);
  }finally{
    refreshRunning=false;
    if(btn){btn.disabled=false;btn.textContent=old}
  }
}

async function authoritativeClear(event,filteredOnly){
  event.preventDefault();
  event.stopImmediatePropagation();
  try{
    await load(false);
    toast('صف با داده واقعی همگام شد',1800);
    if(!window.NewsroomV1?.clearView)throw Error('ماژول پاک‌سازی بارگذاری نشده است');
    await window.NewsroomV1.clearView(filteredOnly);
  }catch(e){
    toast('پاک‌سازی انجام نشد: '+(e?.message||e),12000);
  }
}

function bindAuthoritativeCommands(){
  const refresh=$('refreshBtn');
  if(refresh&&!refresh.dataset.authoritativeBound){
    refresh.dataset.authoritativeBound='1';
    refresh.addEventListener('click',event=>{
      event.preventDefault();
      event.stopImmediatePropagation();
      authoritativeRefresh();
    },true);
  }
  const clearAll=$('clearCurrentView');
  if(clearAll&&!clearAll.dataset.authoritativeBound){
    clearAll.dataset.authoritativeBound='1';
    clearAll.addEventListener('click',event=>authoritativeClear(event,false),true);
  }
  const clearFiltered=$('clearFilteredView');
  if(clearFiltered&&!clearFiltered.dataset.authoritativeBound){
    clearFiltered.dataset.authoritativeBound='1';
    clearFiltered.addEventListener('click',event=>authoritativeClear(event,true),true);
  }
}

window.authoritativeRefresh=authoritativeRefresh;
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bindAuthoritativeCommands);
else bindAuthoritativeCommands();
})();
