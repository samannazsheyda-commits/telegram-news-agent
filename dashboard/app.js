const OWNER='samannazsheyda-commits';
const REPO='telegram-news-agent';
const BRANCH='main';
const RAW=`https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}`;
const API=`https://api.github.com/repos/${OWNER}/${REPO}`;
const GH=`https://github.com/${OWNER}/${REPO}`;

const $=(id)=>document.getElementById(id);
const terminal=new Set(['published_manual','published_auto','rejected_manual','superseded']);
const reasonFa={
  article_or_commentary:'تحلیل / یادداشت سردبیری',
  low_signal:'اهمیت خبری پایین',
  low_signal_or_unapproved_source:'اهمیت پایین یا منبع تأییدنشده',
  duplicate_or_redundant:'تکراری یا بسیار مشابه',
  duplicate_event:'رویداد تکراری',
  bundled_headline:'چند خبر در یک تیتر',
  bundled_or_multi_headline:'چند خبر در یک تیتر',
  translation_failed:'ترجمه ناموفق',
  translation_failed_retry_later:'ترجمه ناموفق؛ قابل بررسی دستی',
  unapproved_source:'منبع تأییدنشده',
  invalid_publish_time:'زمان انتشار نامعتبر',
  stale:'قدیمی',
  not_today_tehran:'مربوط به امروز تهران نیست',
  vague_or_speculative:'مبهم یا گمانه‌زنی',
  question_or_explainer:'پرسشی / توضیحی'
};

function esc(v=''){return String(v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmtDate(v){if(!v)return '—';const d=new Date(v);if(Number.isNaN(d.getTime()))return esc(v);return new Intl.DateTimeFormat('fa-IR',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'}).format(d);}
function tehranDay(v){if(!v)return '';const d=new Date(v);if(Number.isNaN(d.getTime()))return '';return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
function todayTehran(){return tehranDay(new Date().toISOString());}
function statusFa(s){return ({published_manual:'منتشرشده دستی',published_auto:'منتشرشده خودکار',rejected_manual:'رد شده',superseded:'جایگزین‌شده',pending:'در انتظار'})[s]||s||'نامشخص';}

async function getJson(url){const r=await fetch(`${url}${url.includes('?')?'&':'?'}_=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);return r.json();}

function effectiveQueue(queue,history){const done=new Set(history.filter(x=>terminal.has(x.status)).map(x=>x.id));return queue.filter(x=>(x.status||'pending')==='pending'&&!done.has(x.id));}

function renderPending(items){const el=$('pendingList');if(!items.length){el.innerHTML='<div class="empty">فعلاً خبر گیرکرده‌ای در صف نیست.</div>';return;}el.innerHTML=items.slice(0,100).map(r=>{
 const title=r.persian_title||r.original_title||'بدون تیتر';
 const body=r.persian_body||r.original_summary||'';
 const reason=reasonFa[r.reason]||r.reason||'نیازمند بررسی';
 const src=r.source||'منبع نامشخص';
 const sourceLink=r.source_url?`<a href="${esc(r.source_url)}" target="_blank" rel="noopener">منبع اصلی</a>`:'';
 const ghLink=`${GH}/blob/${BRANCH}/data/editorial_queue.json`;
 return `<article class="card"><div class="card-top"><h3>${esc(title)}</h3><span class="badge bad">${esc(reason)}</span></div><div class="meta"><span>${esc(src)}</span><span>${fmtDate(r.published_at_source)}</span><span>ID: ${esc((r.id||'').slice(0,10))}</span></div>${body?`<div class="body">${esc(body)}</div>`:''}<div class="card-links">${sourceLink}<a href="${ghLink}" target="_blank" rel="noopener">بررسی در GitHub</a></div></article>`;
}).join('');}

function renderHistory(items){const el=$('historyList');if(!items.length){el.innerHTML='<div class="empty">تاریخچه‌ای ثبت نشده.</div>';return;}el.innerHTML=items.slice(0,80).map(r=>{
 const title=r.persian_title||r.original_title||'بدون تیتر';
 const good=(r.status||'').startsWith('published');
 const when=r.decision_at||r.updated_at||r.published_at_source;
 return `<article class="card"><div class="card-top"><h3>${esc(title)}</h3><span class="badge ${good?'good':''}">${esc(statusFa(r.status))}</span></div><div class="meta"><span>${esc(r.source||'')}</span><span>${fmtDate(when)}</span>${r.reason?`<span>${esc(reasonFa[r.reason]||r.reason)}</span>`:''}</div></article>`;
}).join('');}

function renderWorkflow(run){if(!run){$('workflowStatus').textContent='نامشخص';return;}const status=run.status==='completed'?(run.conclusion==='success'?'موفق':'ناموفق'):run.status;$('workflowStatus').textContent=status;$('workflowNumber').textContent=run.run_number?`#${run.run_number}`:'—';$('workflowSha').textContent=run.head_sha||'—';$('workflowLink').href=run.html_url||`${GH}/actions`;const health=$('healthBanner');health.classList.remove('loading','good','warn','bad');if(run.status==='completed'&&run.conclusion==='success'){health.classList.add('good');$('healthTitle').textContent='ایجنت سالم است';$('healthText').textContent='آخرین اجرای GitHub Actions با موفقیت تمام شده.';}else if(run.status!=='completed'){health.classList.add('warn');$('healthTitle').textContent='ایجنت در حال اجراست';$('healthText').textContent='آخرین Workflow هنوز تمام نشده.';}else{health.classList.add('bad');$('healthTitle').textContent='آخرین اجرا خطا داشته';$('healthText').textContent='برای جزئیات، تب «سیستم» را باز کن.';}}

async function load(){
 $('refreshBtn').disabled=true;
 try{
  const [queue,history,state,runs]=await Promise.all([
   getJson(`${RAW}/data/editorial_queue.json`),
   getJson(`${RAW}/data/editorial_history.json`),
   getJson(`${RAW}/state.json`),
   getJson(`${API}/actions/workflows/agent.yml/runs?branch=${BRANCH}&per_page=1`)
  ]);
  const q=Array.isArray(queue)?queue:[];const h=Array.isArray(history)?history:[];const effective=effectiveQueue(q,h);const today=todayTehran();
  const published=h.filter(r=>['published_manual','published_auto'].includes(r.status)&&tehranDay(r.decision_at||r.updated_at)===today);
  const rejected=h.filter(r=>['rejected_manual','superseded'].includes(r.status)&&tehranDay(r.decision_at||r.updated_at)===today);
  const last=h.find(r=>['published_manual','published_auto'].includes(r.status));
  $('pendingCount').textContent=effective.length.toLocaleString('fa-IR');
  $('publishedToday').textContent=published.length.toLocaleString('fa-IR');
  $('rejectedToday').textContent=rejected.length.toLocaleString('fa-IR');
  $('lastPublished').textContent=last?fmtDate(last.decision_at||last.updated_at):'—';
  $('statePreview').textContent=JSON.stringify(state,null,2).slice(0,12000);
  renderPending(effective);renderHistory(h);renderWorkflow((runs.workflow_runs||[])[0]);
  $('lastRefresh').textContent=`آخرین بروزرسانی: ${new Intl.DateTimeFormat('fa-IR',{timeStyle:'medium'}).format(new Date())}`;
 }catch(err){const health=$('healthBanner');health.classList.remove('loading','good','warn');health.classList.add('bad');$('healthTitle').textContent='دریافت اطلاعات ناموفق بود';$('healthText').textContent=err.message;}
 finally{$('refreshBtn').disabled=false;}
}

$('runAgentBtn').href=`${GH}/actions/workflows/agent.yml`;
$('queueGitHubLink').href=`${GH}/blob/${BRANCH}/data/editorial_queue.json`;
$('historyGitHubLink').href=`${GH}/blob/${BRANCH}/data/editorial_history.json`;
$('refreshBtn').addEventListener('click',load);
document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));btn.classList.add('active');$(btn.dataset.tab).classList.add('active');}));
load();
setInterval(load,60000);
