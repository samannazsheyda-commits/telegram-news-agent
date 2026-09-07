const OWNER='samannazsheyda-commits',REPO='telegram-news-agent',BRANCH='main';
const RAW=`https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}`;
const API=`https://api.github.com/repos/${OWNER}/${REPO}`;
const TOKEN_KEY='bikhabar_contents_token';
const $=id=>document.getElementById(id);
const TERMINAL_EDITORIAL=new Set(['published_manual','published_auto','rejected_manual','superseded']);
const TERMINAL_COMMAND=new Set(['succeeded','failed','reconciled']);
const activeCommands=new Map();
const hiddenItems=new Set();
let queue=[],history=[],filtered=[],renderLimit=60,toastTimer=null,connectionValidated=false;

function esc(v=''){return String(v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function fmt(v){if(!v)return'—';const d=new Date(v);if(Number.isNaN(d.getTime()))return esc(v);return new Intl.DateTimeFormat('fa-IR',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'}).format(d)}
function day(v){if(!v)return'';const d=new Date(v);if(Number.isNaN(d.getTime()))return'';return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(d)}
function token(){return localStorage.getItem('bikhabar_contents_token')||''}
function authHeaders(value=token()){return{'Accept':'application/vnd.github+json','Authorization':'Bearer '+value,'X-GitHub-Api-Version':'2022-11-28'}}
function ghHeaders(value=token()){return{...authHeaders(value),'Content-Type':'application/json'}}
function b64Unicode(text){const bytes=new TextEncoder().encode(text);let bin='';bytes.forEach(b=>bin+=String.fromCharCode(b));return btoa(bin)}
async function getJson(url){const r=await fetch(url+(url.includes('?')?'&':'?')+'_='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(`${r.status} ${r.statusText}`);return r.json()}
function commandId(){return crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(36).slice(2)}`}
async function githubError(r){let detail='';try{const data=await r.json();detail=data.message||JSON.stringify(data)}catch{try{detail=await r.text()}catch{}}return `GitHub ${r.status}${detail?': '+detail.slice(0,350):''}`}

function draftKey(id){return`bikhabar_draft_${id}`}
function saveDraft(id,title,body){localStorage.setItem(draftKey(id),JSON.stringify({title,body,at:Date.now()}))}
function restoreDraft(id){try{return JSON.parse(localStorage.getItem(draftKey(id))||'null')}catch{return null}}
function clearDraft(id){localStorage.removeItem(draftKey(id))}
function setConnection(text,kind=''){const el=$('connectionBadge');el.textContent=text;el.className='badge '+kind}
function toast(message,actionText='',action=null,duration=6000){clearTimeout(toastTimer);const el=$('toast'),b=$('toastAction');$('toastText').textContent=message;b.textContent=actionText;b.style.display=actionText?'inline':'none';b.onclick=action||null;el.classList.add('show');toastTimer=setTimeout(()=>el.classList.remove('show'),duration)}

async function validateConnection(candidate=token()){
  const value=(candidate||'').trim();
  if(!value){connectionValidated=false;throw Error('توکن GitHub وارد نشده است')}
  const r=await fetch(`${API}/contents/data/editorial_queue.json?ref=${BRANCH}&_=${Date.now()}`,{headers:authHeaders(value),cache:'no-store'});
  if(!r.ok){connectionValidated=false;throw Error(await githubError(r))}
  connectionValidated=true;
  return true;
}

async function createCommand(payload,attempt=0){
  if(!token()){$('connectSheet').classList.add('open');setConnection('مشاهده فقط','bad');throw Error('اتصال GitHub برقرار نیست')}
  if(!connectionValidated)await validateConnection();
  const id=payload.command_id||commandId();
  const command={...payload,command_id:id,created_at:new Date().toISOString()};
  const path=`panel_commands/${id}.json`;
  const body={message:`panel: ${command.action} ${command.item_id.slice(0,10)}`,content:b64Unicode(JSON.stringify(command,null,2)),branch:BRANCH};
  const r=await fetch(`${API}/contents/${path}`,{method:'PUT',headers:ghHeaders(),body:JSON.stringify(body)});
  if((r.status===409||r.status===422)&&attempt===0)return createCommand({...payload,command_id:commandId()},1);
  if(!r.ok){const message=await githubError(r);if(r.status===401||r.status===403){connectionValidated=false;setConnection('مجوز Contents مشکل دارد','bad');$('connectSheet').classList.add('open')}throw Error(message)}
  return id;
}

async function pollCommandResult(id,timeoutMs=90000){
  const started=Date.now();
  while(Date.now()-started<timeoutMs){
    try{const r=await fetch(`${RAW}/panel_results/${id}.json?_=${Date.now()}`,{cache:'no-store'});if(r.ok){const data=await r.json();if(TERMINAL_COMMAND.has(data.status))return data}}catch{}
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
  return{command_id:id,status:'timeout',message:'نتیجه هنوز نهایی نشده است'};
}

function terminalIds(){return new Set(history.filter(x=>TERMINAL_EDITORIAL.has(x.status)).map(x=>x.id))}
function rawPendingIds(){return new Set(queue.filter(x=>(x.status||'pending')==='pending').map(x=>x.id))}
function effectiveQueue(){const done=terminalIds();return queue.filter(x=>(x.status||'pending')==='pending'&&!done.has(x.id)&&!hiddenItems.has(x.id))}
function originalTitle(r){return r.persian_title||r.original_title||''}
function originalBody(r){return r.persian_body||r.original_summary||''}

function applyFilters(){
  const q=$('queueSearch').value.trim().toLowerCase(),src=$('sourceFilter').value,reason=$('reasonFilter').value,order=$('sortOrder').value;
  filtered=effectiveQueue().filter(r=>{const hay=`${r.persian_title||r.original_title||''} ${r.persian_body||r.original_summary||''} ${r.source||''}`.toLowerCase();return(!q||hay.includes(q))&&(!src||r.source===src)&&(!reason||(r.rejection_reason||r.reason||'')===reason)});
  filtered.sort((a,b)=>{const aa=new Date(a.published_at_source||a.updated_at||0),bb=new Date(b.published_at_source||b.updated_at||0);return order==='oldest'?aa-bb:bb-aa});renderQueue();
}

function cardHtml(r){const d=restoreDraft(r.id),title=d?.title??originalTitle(r),body=d?.body??originalBody(r),edited=!!d;return`<article class="card" data-id="${esc(r.id)}"><div class="card-head"><div style="flex:1"><input class="title-input" data-role="title" value="${esc(title)}" aria-label="تیتر خبر"><div class="meta"><span class="badge">${esc(r.source||'منبع')}</span><span>${fmt(r.published_at_source)}</span>${r.rejection_reason?`<span class="reason">${esc(r.rejection_reason)}</span>`:''}<span class="edited" ${edited?'':'hidden'}>ویرایش شده</span></div></div></div><textarea class="body-input" data-role="body" aria-label="متن خبر">${esc(body)}</textarea><div class="card-actions"><button class="btn green" data-action="publish">انتشار</button><button class="btn red" data-action="reject">رد</button>${r.source_url?`<a class="btn ghost" href="${esc(r.source_url)}" target="_blank" rel="noopener">منبع</a>`:''}<button class="btn ghost draft-reset" data-action="reset" ${edited?'':'hidden'}>بازگشت به متن اولیه</button></div></article>`}
function renderQueue(){const el=$('queueList');if(!filtered.length){el.innerHTML='<div class="empty">فعلاً خبری در صف نیست.</div>';updateStats();return}const visible=filtered.slice(0,renderLimit);el.innerHTML=visible.map(cardHtml).join('')+(filtered.length>renderLimit?`<button class="btn ghost" data-global-action="more">نمایش ${Math.min(40,filtered.length-renderLimit).toLocaleString('fa-IR')} خبر بعدی</button>`:'');updateStats()}
function renderProcessing(){const rows=[...activeCommands.values()];$('processingList').innerHTML=rows.length?rows.map(x=>`<article class="card processing"><strong>${esc(x.title||originalTitle(x.item))}</strong><div class="meta"><span>${x.action==='publish'?'در حال انتشار':'در حال رد'}</span><span>${esc(x.message||'در انتظار پردازش')}</span><span>${fmt(x.startedAt)}</span></div></article>`).join(''):'<div class="empty">فرمان فعالی نیست.</div>'}
function historyCard(r){return`<article class="card"><strong>${esc(r.final_persian_title||r.persian_title||r.original_title||'بدون تیتر')}</strong><div class="meta"><span>${esc(r.source||'')}</span><span>${fmt(r.decision_at||r.updated_at)}</span><span>${esc(r.status||'')}</span></div></article>`}
function renderHistoryViews(){const p=history.filter(x=>['published_manual','published_auto'].includes(x.status)).slice(0,80),r=history.filter(x=>['rejected_manual','superseded'].includes(x.status)).slice(0,80);$('publishedList').innerHTML=p.length?p.map(historyCard).join(''):'<div class="empty">موردی نیست.</div>';$('rejectedList').innerHTML=r.length?r.map(historyCard).join(''):'<div class="empty">موردی نیست.</div>'}
function updateStats(){const today=day(new Date().toISOString());$('pendingCount').textContent=effectiveQueue().length.toLocaleString('fa-IR');$('processingCount').textContent=activeCommands.size.toLocaleString('fa-IR');$('publishedCount').textContent=history.filter(x=>['published_manual','published_auto'].includes(x.status)&&day(x.decision_at||x.updated_at)===today).length.toLocaleString('fa-IR');$('rejectedCount').textContent=history.filter(x=>['rejected_manual','superseded'].includes(x.status)&&day(x.decision_at||x.updated_at)===today).length.toLocaleString('fa-IR')}
function hideCard(id){hiddenItems.add(id);const card=document.querySelector(`[data-id="${CSS.escape(id)}"]`);if(card){card.classList.add('removing');setTimeout(applyFilters,120)}else applyFilters()}
function restoreRejectedCard(item){hiddenItems.delete(item.id);applyFilters()}
function restorePublishCard(snapshot){hiddenItems.delete(snapshot.item.id);saveDraft(snapshot.item.id,snapshot.title,snapshot.body);applyFilters()}
function optimisticReject(item){hideCard(item.id);return true}
function optimisticPublish(item,title,body,cmd){hiddenItems.add(item.id);activeCommands.set(cmd,{action:'publish',item,title,body,message:'فرمان ثبت می‌شود…',startedAt:new Date().toISOString()});applyFilters();renderProcessing();updateStats()}
function rekeyActiveCommand(oldId,newId){if(oldId===newId)return;const value=activeCommands.get(oldId);if(!value)return;activeCommands.delete(oldId);activeCommands.set(newId,value);renderProcessing()}

async function continueWatching(cmd){const result=await pollCommandResult(cmd,300000);if(result.status==='timeout'){const pending=activeCommands.get(cmd);if(pending){pending.message='هنوز در حال بررسی؛ وضعیت را دوباره چک کن';renderProcessing()}return}await reconcileCommandResult(cmd,result)}
async function reconcileCommandResult(cmd,result){const pending=activeCommands.get(cmd);if(!pending)return;if(result.status==='timeout'){pending.message='زمان‌بر شده؛ پردازش ادامه دارد';renderProcessing();toast('پردازش طول کشیده؛ خبر دوباره وارد صف نشده است');void continueWatching(cmd);return}activeCommands.delete(cmd);if(result.status==='failed'){if(pending.action==='publish')restorePublishCard(pending);else restoreRejectedCard(pending.item);toast((pending.action==='publish'?'انتشار':'رد')+' ناموفق بود: '+(result.message||'خطای نامشخص'))}else{clearDraft(pending.item.id);toast(result.status==='reconciled'?'وضعیت خبر با کانال هماهنگ شد':(pending.action==='publish'?'انتشار در تلگرام تأیید شد':'خبر رد شد'));await load(false)}renderProcessing();updateStats()}

async function rejectItem(item){
  optimisticReject(item);
  const provisional=commandId();activeCommands.set(provisional,{action:'reject',item,title:originalTitle(item),body:'',message:'ثبت فوری فرمان رد…',startedAt:new Date().toISOString()});renderProcessing();updateStats();
  try{const actual=await createCommand({command_id:provisional,action:'reject',item_id:item.id,title:'',body:''});rekeyActiveCommand(provisional,actual);const pending=activeCommands.get(actual);if(pending){pending.message='در حال نهایی‌کردن رد';renderProcessing()}await reconcileCommandResult(actual,await pollCommandResult(actual))}
  catch(e){activeCommands.delete(provisional);restoreRejectedCard(item);renderProcessing();updateStats();toast('رد ثبت نشد: '+e.message,'',null,10000)}
}

async function publishItem(item,card){
  const title=card.querySelector('[data-role="title"]').value.trim(),body=card.querySelector('[data-role="body"]').value.trim();if(!title){card.querySelector('[data-role="title"]').focus();toast('تیتر نمی‌تواند خالی باشد');return}if(!item.source_url){toast('لینک منبع برای انتشار لازم است');return}
  const provisional=commandId();optimisticPublish(item,title,body,provisional);
  try{const actual=await createCommand({command_id:provisional,action:'publish',item_id:item.id,title,body});rekeyActiveCommand(provisional,actual);const pending=activeCommands.get(actual);if(pending){pending.message='در انتظار تأیید تلگرام';renderProcessing()}await reconcileCommandResult(actual,await pollCommandResult(actual))}
  catch(e){const pending=activeCommands.get(provisional);activeCommands.delete(provisional);if(pending)restorePublishCard(pending);renderProcessing();updateStats();toast('انتشار ثبت نشد: '+e.message,'',null,10000)}
}

function resetDraft(item,card){clearDraft(item.id);card.querySelector('[data-role="title"]').value=originalTitle(item);card.querySelector('[data-role="body"]').value=originalBody(item);card.querySelector('.edited').hidden=true;card.querySelector('[data-action="reset"]').hidden=true}
function populateFilters(){const oldSource=$('sourceFilter').value,oldReason=$('reasonFilter').value;const src=[...new Set(queue.map(x=>x.source).filter(Boolean))].sort(),reasons=[...new Set(queue.map(x=>x.rejection_reason||x.reason).filter(Boolean))].sort();$('sourceFilter').innerHTML='<option value="">همه منابع</option>'+src.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');$('reasonFilter').innerHTML='<option value="">همه دلایل</option>'+reasons.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');if(src.includes(oldSource))$('sourceFilter').value=oldSource;if(reasons.includes(oldReason))$('reasonFilter').value=oldReason}
function reconcileHiddenWithServer(){const done=terminalIds(),pending=rawPendingIds();for(const id of [...hiddenItems]){if(done.has(id)||!pending.has(id))hiddenItems.delete(id)}}
async function load(showLoading=true){try{if(showLoading&&queue.length===0)$('queueList').innerHTML='<div class="skeleton"></div><div class="skeleton"></div>';const[q,h]=await Promise.all([getJson(`${RAW}/data/editorial_queue.json`),getJson(`${RAW}/data/editorial_history.json`)]);queue=Array.isArray(q)?q:[];history=Array.isArray(h)?h:[];reconcileHiddenWithServer();populateFilters();applyFilters();renderHistoryViews();$('staleBadge').hidden=true;$('lastRefresh').textContent='بروزرسانی '+new Intl.DateTimeFormat('fa-IR',{timeStyle:'medium'}).format(new Date())}catch(e){toast('داده تازه دریافت نشد؛ نمایش قبلی حفظ شد');$('staleBadge').hidden=false}}
async function loadSystem(){try{const[runs,state]=await Promise.all([getJson(`${API}/actions/workflows/agent.yml/runs?per_page=1`),getJson(`${RAW}/state.json`)]);const r=runs.workflow_runs?.[0];$('systemWorkflow').textContent=r?`${r.status}${r.conclusion?' / '+r.conclusion:''}`:'—';$('systemRun').textContent=r?.run_number??'—';$('systemRuntime').textContent='runtime_v13';$('systemState').textContent=`news_seen: ${(state.news_seen||[]).length} | car: ${state.car_last_sent_date||'—'} | phone: ${state.phone_flagships_last_sent_date||'—'}`}catch{$('systemWorkflow').textContent='خطا در دریافت'}}

async function connect(){
  const t=$('tokenInput').value.trim();if(!t)return;
  setConnection('در حال بررسی…','');
  try{await validateConnection(t);localStorage.setItem('bikhabar_contents_token',t);$('tokenInput').value='';$('connectSheet').classList.remove('open');setConnection('GitHub متصل','good');toast('اتصال برقرار شد. برای کارکرد دکمه‌ها، توکن باید Contents: Read and write داشته باشد.')}
  catch(e){connectionValidated=false;localStorage.removeItem('bikhabar_contents_token');setConnection('اتصال ناموفق','bad');toast(e.message,'',null,12000)}
}
function disconnect(){connectionValidated=false;localStorage.removeItem('bikhabar_contents_token');setConnection('مشاهده فقط','bad');$('connectSheet').classList.add('open')}
async function restoreConnection(){if(!token()){$('connectSheet').classList.add('open');setConnection('مشاهده فقط','bad');return}setConnection('بررسی اتصال…','');try{await validateConnection();setConnection('GitHub متصل','good');$('connectSheet').classList.remove('open')}catch(e){connectionValidated=false;setConnection('اتصال نیاز به اصلاح دارد','bad');$('connectSheet').classList.add('open');toast(e.message,'',null,12000)}}

document.addEventListener('click',e=>{const tab=e.target.closest('[data-view]');if(tab){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===tab));document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${tab.dataset.view}`));if(tab.dataset.view==='system')loadSystem();return}const more=e.target.closest('[data-global-action="more"]');if(more){renderLimit+=40;renderQueue();return}const action=e.target.closest('[data-action]');if(!action)return;const card=action.closest('.card[data-id]'),item=queue.find(x=>x.id===card?.dataset.id);if(!item)return;if(action.dataset.action==='publish')publishItem(item,card);if(action.dataset.action==='reject')rejectItem(item);if(action.dataset.action==='reset')resetDraft(item,card)});
document.addEventListener('input',e=>{const card=e.target.closest('.card[data-id]');if(!card||!['title','body'].includes(e.target.dataset.role))return;clearTimeout(card._draftTimer);card._draftTimer=setTimeout(()=>{saveDraft(card.dataset.id,card.querySelector('[data-role="title"]').value,card.querySelector('[data-role="body"]').value);card.querySelector('.edited').hidden=false;card.querySelector('[data-action="reset"]').hidden=false},250)});
['queueSearch','sourceFilter','sortOrder','reasonFilter'].forEach(id=>$(id).addEventListener(id==='queueSearch'?'input':'change',()=>{renderLimit=60;applyFilters()}));
$('clearFilters').onclick=()=>{$('queueSearch').value='';$('sourceFilter').value='';$('reasonFilter').value='';$('sortOrder').value='newest';renderLimit=60;applyFilters()};
$('refreshBtn').onclick=()=>load(false);$('connectBtn').onclick=()=>$('connectSheet').classList.toggle('open');$('saveTokenBtn').onclick=connect;$('disconnectBtn').onclick=disconnect;$('tokenInput').addEventListener('keydown',e=>{if(e.key==='Enter')connect()});
restoreConnection();load();setInterval(()=>{if(document.visibilityState==='visible')load(false)},15000);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){load(false);if(token()&&!connectionValidated)restoreConnection()}});
