(()=>{
'use strict';

const SOURCE_FA={
  'Reuters':'رویترز','Bloomberg':'بلومبرگ','Times of Israel':'تایمز اسرائیل','The Times of Israel':'تایمز اسرائیل',
  'Associated Press':'آسوشیتدپرس','AP':'آسوشیتدپرس','AFP':'خبرگزاری فرانسه','BBC':'بی‌بی‌سی','BBC World':'بی‌بی‌سی ورلد',
  'CNN':'سی‌ان‌ان','France 24':'فرانس ۲۴','Al Jazeera English':'الجزیره','Al Arabiya English':'العربیه',
  'The New York Times':'نیویورک تایمز','New York Times':'نیویورک تایمز','Financial Times':'فایننشال تایمز',
  'Sky News':'اسکای نیوز','NBC News':'ان‌بی‌سی نیوز','CBS News':'سی‌بی‌اس نیوز','ABC News':'ای‌بی‌سی نیوز','Fox News':'فاکس نیوز',
  'DW News':'دویچه‌وله','The Guardian':'گاردین','Washington Post':'واشنگتن پست','Wall Street Journal':'وال‌استریت ژورنال',
  'Haaretz':'هاآرتص','Axios':'اکسیوس','Jerusalem Post':'جروزالم پست','Israel Hayom':'اسرائیل هیوم',
  'CENTCOM':'سنتکام','White House':'کاخ سفید','US Treasury':'وزارت خزانه‌داری آمریکا','US State Department':'وزارت خارجه آمریکا',
  'State Department':'وزارت خارجه آمریکا','TankerTrackers':'تنکر ترکرز','NOTAM':'نوتام','Tabz Live':'تبز لایو'
};
const DEFAULT_SETTINGS={
  version:1,emergency_lock:false,auto_publish:true,quiet_mode:false,quiet_start:'00:00',quiet_end:'07:00',
  freshness_hours:3,dedup_mode:'strict',earthquake_min:2,earthquake_breaking:4,notam_sensitivity:'high',
  market:{btc:true,usdt:true,oil:true,gold:true,cars:true,phones:true},
  alerts:{breaking_sound:false,source_failure:true},ui:{density:'comfortable',show_original:false},sources:{}
};
let newsroomSettings=structuredClone?structuredClone(DEFAULT_SETTINGS):JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
let activeCardId='';

const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
const byId=id=>document.getElementById(id);
const faNum=n=>(Number(n)||0).toLocaleString('fa-IR');
const ascii=/[A-Za-z]/;
function localSource(v=''){
  let raw=String(v||'').trim();
  const hasX=/\s*\/\s*X\s*$/i.test(raw);raw=raw.replace(/\s*\/\s*(X|Telegram)\s*$/i,'').trim();
  let out=SOURCE_FA[raw]||raw||'منبع خبری';if(ascii.test(out))out='منبع خبری';return hasX?`${out} / ایکس`:out;
}
function textOf(r){return `${r?.persian_title||''} ${r?.persian_body||''} ${r?.original_title||''} ${r?.original_summary||''}`.toLowerCase()}
function categoryOf(r){const t=textOf(r);if(/زلزله|earthquake/.test(t))return'زلزله';if(/نوتام|notam|پرواز|airspace|flight/.test(t))return'پرواز و نوتام';if(/هسته|nuclear|uranium/.test(t))return'هسته‌ای';if(/تحریم|sanction/.test(t))return'تحریم';if(/نفت|oil|tanker|energy/.test(t))return'نفت و انرژی';if(/بیت.?کوین|تتر|bitcoin|usdt|market/.test(t))return'بازار';if(/اسرائیل|israel/.test(t))return'اسرائیل';if(/آمریکا|united states|u\.s\.|centcom|white house/.test(t))return'آمریکا';if(/حمله|موشک|پهپاد|انفجار|جنگ|attack|strike|missile|drone|explosion/.test(t))return'جنگ و درگیری';if(/ایران|iran/.test(t))return'ایران';return'سایر'}
function priorityOf(r){const t=textOf(r);const src=String(r?.source||'');if(/حمله|موشک|پهپاد|انفجار|بمباران|attack|strike|missile|explosion/.test(t))return'فوری';if(/CENTCOM|White House|Reuters|Bloomberg|Times of Israel|هسته|تحریم|نوتام|airspace/.test(`${src} ${t}`))return'مهم';return'عادی'}
function sourceTime(r){const v=r?.published_at_source||r?.discovered_at||r?.updated_at;const d=new Date(v||0);return Number.isNaN(d.getTime())?0:d.getTime()}
function todayRows(){try{return effectiveQueue()}catch{return Array.isArray(queue)?queue:[]}}
function todayHistory(statuses){const now=day(new Date().toISOString());return (Array.isArray(history)?history:[]).filter(x=>statuses.includes(x.status)&&day(x.decision_at||x.updated_at)===now)}
function newestRow(){return [...todayRows()].sort((a,b)=>sourceTime(b)-sourceTime(a))[0]||null}

function commandBarHtml(){return `<section class="nr-commandbar" id="newsroomCommandBar">
  <article class="nr-live-card primary"><span class="nr-pulse" id="nrAgentPulse"></span><div><span>وضعیت اتاق خبر</span><strong id="nrAgentHealth">در حال بررسی</strong><small id="nrHealthDetail">—</small></div></article>
  <article class="nr-live-card"><span>خبرهای امروز</span><strong id="nrTodayTotal">۰</strong></article>
  <article class="nr-live-card"><span>فوری ۳۰ دقیقه اخیر</span><strong id="nrBreaking30">۰</strong></article>
  <article class="nr-live-card"><span>در انتظار تصمیم</span><strong id="nrDecisionCount">۰</strong></article>
  <article class="nr-live-card"><span>منتشرشده امروز</span><strong id="nrPublishedToday">۰</strong></article>
  <article class="nr-live-card"><span>آخرین خبر منبع</span><strong id="nrLatestTime">—</strong></article>
</section>`}
function railHtml(){return `<aside class="nr-rail" id="situationRail">
  <section class="nr-rail-card nr-breaking"><h3>وضعیت لحظه‌ای</h3><div class="nr-rail-row"><span>فوری‌های صف</span><strong id="nrRailBreaking">۰</strong></div><div class="nr-rail-row"><span>آخرین موضوع</span><strong id="nrRailTopic">—</strong></div><div class="nr-rail-row"><span>آخرین منبع</span><strong id="nrRailSource">—</strong></div></section>
  <section class="nr-rail-card"><h3>سلامت سیستم</h3><div class="nr-rail-row"><span>اتصال پنل</span><strong id="nrRailConnection">—</strong></div><div class="nr-rail-row"><span>فرمان فعال</span><strong id="nrRailCommands">۰</strong></div><div class="nr-rail-row"><span>آخرین دریافت</span><strong id="nrRailRefresh">—</strong></div></section>
  <section class="nr-rail-card"><h3>میانبرها</h3><div class="nr-rail-row"><span>خبر بعدی / قبلی</span><strong>J / K</strong></div><div class="nr-rail-row"><span>پیش‌نمایش</span><strong>P</strong></div><div class="nr-rail-row"><span>اسکن فوری</span><strong>F</strong></div></section>
</aside>`}

function ensureShell(){
  const top=document.querySelector('.top');if(top&&!byId('newsroomCommandBar'))top.insertAdjacentHTML('afterend',commandBarHtml());
  const stats=document.querySelector('.stats');const tabs=document.querySelector('.tabs');if(!stats||!tabs)return;
  if(!byId('nrWorkspace')){
    const wrapper=document.createElement('div');wrapper.id='nrWorkspace';wrapper.className='nr-workspace';
    const main=document.createElement('div');main.className='nr-main';main.id='nrMain';
    stats.parentNode.insertBefore(wrapper,stats);wrapper.appendChild(main);main.appendChild(stats);main.appendChild(tabs);
    let node=wrapper.nextSibling;while(node){const next=node.nextSibling;if(node.id==='lastRefresh'||node.classList?.contains('meta'))break;if(node.matches?.('.view'))main.appendChild(node);node=next}
    wrapper.insertAdjacentHTML('beforeend',railHtml());
  }
}
function ensureTabsAndViews(){
  const tabs=document.querySelector('.tabs');if(!tabs)return;
  const defs=[['analytics','تحلیل'],['settings','تنظیمات']];
  for(const [view,label] of defs){if(!tabs.querySelector(`[data-view="${view}"]`))tabs.insertAdjacentHTML('beforeend',`<button class="tab" data-view="${view}">${label}</button>`)}
  const main=byId('nrMain')||document.querySelector('.app');
  if(!byId('view-analytics'))main.insertAdjacentHTML('beforeend',`<section id="view-analytics" class="view"><div id="nrAnalytics"></div></section>`);
  if(!byId('view-settings'))main.insertAdjacentHTML('beforeend',`<section id="view-settings" class="view"><div id="nrSettings"></div></section>`);
  if(!byId('nrListTools'))tabs.insertAdjacentHTML('afterend',`<div class="nr-list-tools" id="nrListTools"><strong class="nr-list-title" id="nrListTitle">در انتظار</strong><button class="btn nr-filter-clear" id="clearFilteredView">پاک کردن نتایج فیلترشده</button><button class="btn nr-danger" id="clearCurrentView">پاک کردن همه</button></div>`);
  qsa('.tab').forEach(tab=>{if(tab.dataset.nrBound)return;tab.dataset.nrBound='1';tab.addEventListener('click',()=>setTimeout(()=>{syncListTools();renderAnalytics();renderSettings()},0))});
}

function decorateCards(){
  qsa('#queueList .card').forEach(card=>{
    const id=card.dataset.id;if(!id||card.dataset.nrReady)return;card.dataset.nrReady='1';
    const item=(Array.isArray(queue)?queue:[]).find(x=>String(x.id)===String(id));if(!item)return;
    const badge=card.querySelector('.meta .badge');if(badge)badge.textContent=localSource(item.source);
    const meta=card.querySelector('.meta');if(meta){const p=priorityOf(item),c=categoryOf(item);meta.insertAdjacentHTML('beforeend',`<span class="nr-chip ${p==='فوری'?'hot':p==='مهم'?'important':''}">${p}</span><span class="nr-chip">${c}</span>`) }
    const actions=card.querySelector('.card-actions');if(actions){actions.insertAdjacentHTML('beforeend',`<button class="btn ghost" data-nr-action="hold">نگه‌دار</button><button class="btn ghost" data-nr-action="preview">پیش‌نمایش</button>`)}
    card.addEventListener('mouseenter',()=>activeCardId=id);card.addEventListener('focusin',()=>activeCardId=id);
  })
  qsa('[data-nr-action="hold"]').forEach(btn=>{if(btn.dataset.bound)return;btn.dataset.bound='1';btn.addEventListener('click',e=>{const card=e.target.closest('.card');toggleHold(card?.dataset.id,e.target)})});
  qsa('[data-nr-action="preview"]').forEach(btn=>{if(btn.dataset.bound)return;btn.dataset.bound='1';btn.addEventListener('click',e=>openPreview(e.target.closest('.card')?.dataset.id))});
}
function toggleHold(id,btn){if(!id)return;const key=`bikhabar_hold_${id}`;const held=localStorage.getItem(key)==='1';localStorage.setItem(key,held?'0':'1');btn.textContent=held?'نگه‌دار':'نگه‌داشته شد';btn.classList.toggle('nr-filter-clear',!held);toast(held?'خبر از حالت نگه‌دار خارج شد':'خبر برای بررسی بعدی نگه داشته شد')}

function modal(){let el=byId('nrModal');if(el)return el;document.body.insertAdjacentHTML('beforeend',`<div class="nr-modal" id="nrModal" aria-hidden="true"><div class="nr-dialog"><h2 id="nrModalTitle"></h2><div id="nrModalBody"></div><div class="nr-dialog-actions" id="nrModalActions"></div></div></div>`);el=byId('nrModal');el.addEventListener('click',e=>{if(e.target===el)closeModal()});return el}
function closeModal(){const m=byId('nrModal');if(m){m.classList.remove('show');m.setAttribute('aria-hidden','true')}}
function showModal(title,body,actions){const m=modal();byId('nrModalTitle').textContent=title;byId('nrModalBody').innerHTML=body;const a=byId('nrModalActions');a.innerHTML='';actions.forEach(x=>{const b=document.createElement('button');b.className=x.className||'btn';b.textContent=x.label;b.onclick=x.onClick;a.appendChild(b)});m.classList.add('show');m.setAttribute('aria-hidden','false')}
function confirmDanger(label,count){return new Promise(resolve=>{const step1=()=>showModal('تأیید نهایی',`<p class="nr-danger-copy">این عمل روی <strong class="nr-count-pill">${faNum(count)}</strong> مورد اعمال می‌شود.</p><p>برای جلوگیری از حذف اشتباهی، یک بار دیگر تأیید کن.</p>`,[{label:'انصراف',className:'btn ghost',onClick:()=>{closeModal();resolve(false)}},{label:'بله، انجام بده',className:'btn red',onClick:()=>{closeModal();resolve(true)}}]);showModal(label,`<p>تعداد موارد انتخاب‌شده: <strong class="nr-count-pill">${faNum(count)}</strong></p><p>این عملیات برگشت مستقیم ندارد و فقط پس از تأیید دوم اجرا می‌شود.</p>`,[{label:'انصراف',className:'btn ghost',onClick:()=>{closeModal();resolve(false)}},{label:'ادامه',className:'btn nr-danger',onClick:step1}])})}

function previewText(item,title){const src=localSource(item.source);const date=fmt(item.published_at_source);const flags=priorityOf(item)==='فوری'?'🛑':'⚪️';return `${src}: ${title.trim()}\n\n⏰ ${date}\n📌 لینک منبع خبر\n\n📡 بی‌خبر ←\nمانیتور تحولات ایران\n\n${flags}`}
function openPreview(id){const item=(Array.isArray(queue)?queue:[]).find(x=>String(x.id)===String(id));if(!item)return;const card=document.querySelector(`.card[data-id="${CSS.escape(String(id))}"]`);const title=card?.querySelector('[data-role="title"]')?.value||item.persian_title||item.original_title||'';showModal('پیش‌نمایش تلگرام',`<div class="nr-preview">${esc(previewText(item,title))}</div><p class="nr-toast-note">آدرس واقعی منبع پشت عبارت فارسی «لینک منبع خبر» قرار می‌گیرد و در متن دیده نمی‌شود.</p>`,[{label:'بستن',className:'btn',onClick:closeModal}])}

function activeView(){return document.querySelector('.tab.active')?.dataset.view||'pending'}
function idsForView(view,filteredOnly=false){if(view==='pending')return (filteredOnly?(Array.isArray(filtered)?filtered:[]):todayRows()).map(x=>x.id).filter(Boolean);if(view==='published')return todayHistory(['published_manual','published_auto']).map(x=>x.id).filter(Boolean);if(view==='rejected')return todayHistory(['rejected_manual','superseded']).map(x=>x.id).filter(Boolean);return[]}
async function clearView(filteredOnly=false){const view=activeView();if(view==='processing'){const count=activeCommands?.size||0;if(!count){toast('فرمان فعالی برای پاک کردن نمایش وجود ندارد');return}if(await confirmDanger('پاک کردن نمایش «در حال انجام»',count)){activeCommands.clear();renderProcessing();updateStats();toast('نمایش فرمان‌های در حال انجام پاک شد؛ اجرای GitHub لغو نشد')}return}
  const ids=idsForView(view,filteredOnly);if(!ids.length){toast('موردی برای پاک کردن نیست');return}if(!requireConnection({type:'clear'}))return;
  const label=filteredOnly?'پاک کردن نتایج فیلترشده':'پاک کردن همه موارد این بخش';if(!(await confirmDanger(label,ids.length)))return;
  try{const scope=view==='pending'?'pending':view;const id=await createCommand({action:'clear',item_id:'',scope,ids,title:'',body:''});toast('فرمان پاک‌سازی ثبت شد');const result=await pollCommandResult(id,120000);if(result.status==='failed')throw Error(result.message||'پاک‌سازی ناموفق بود');await load(false);renderAnalytics();renderSituation();toast(result.message||'پاک‌سازی انجام شد')}catch(e){toast('پاک‌سازی انجام نشد: '+e.message,12000)}
}
function syncListTools(){const view=activeView();const titles={pending:'در انتظار تصمیم',processing:'در حال انجام',published:'منتشرشده امروز',rejected:'ردشده امروز',analytics:'تحلیل عملکرد',settings:'تنظیمات اتاق خبر',system:'سلامت سیستم'};const t=byId('nrListTitle');if(t)t.textContent=titles[view]||view;const tools=byId('nrListTools');if(!tools)return;const isList=['pending','processing','published','rejected'].includes(view);tools.querySelector('#clearCurrentView').style.display=isList?'':'none';tools.querySelector('#clearFilteredView').style.display=view==='pending'?'':'none'}

function renderSituation(){const rows=todayRows();const newest=newestRow();const breaking=rows.filter(x=>priorityOf(x)==='فوری');const halfHour=Date.now()-30*60*1000;const breaking30=breaking.filter(x=>sourceTime(x)>=halfHour).length;const pub=todayHistory(['published_manual','published_auto']).length;const rej=todayHistory(['rejected_manual','superseded']).length;
  const set=(id,v)=>{const e=byId(id);if(e)e.textContent=v};set('nrTodayTotal',faNum(rows.length+pub+rej));set('nrBreaking30',faNum(breaking30));set('nrDecisionCount',faNum(rows.length));set('nrPublishedToday',faNum(pub));set('nrLatestTime',newest?fmt(newest.published_at_source).split('،').pop()?.trim()||fmt(newest.published_at_source):'—');set('nrRailBreaking',faNum(breaking.length));set('nrRailTopic',newest?categoryOf(newest):'—');set('nrRailSource',newest?localSource(newest.source):'—');set('nrRailCommands',faNum(activeCommands?.size||0));set('nrRailConnection',connectionValidated?'برقرار':'نیاز به اتصال');set('nrRailRefresh',new Intl.DateTimeFormat('fa-IR',{timeStyle:'short'}).format(new Date()));
  const health=byId('nrAgentHealth'),pulse=byId('nrAgentPulse'),detail=byId('nrHealthDetail');if(health){health.textContent=connectionValidated?'آنلاین و آماده':'پنل در حالت مشاهده';pulse?.classList.toggle('bad',!connectionValidated);if(detail)detail.textContent=newest?`آخرین منبع: ${localSource(newest.source)} — ${fmt(newest.published_at_source)}`:'خبر تازه‌ای در صف نیست'}
}

function sourceStats(){const all=[...(Array.isArray(queue)?queue:[]),...(Array.isArray(history)?history:[])];const map=new Map();for(const r of all){const s=localSource(r.source);const x=map.get(s)||{source:s,total:0,published:0,rejected:0,pending:0};x.total++;if(['published_manual','published_auto'].includes(r.status))x.published++;else if(['rejected_manual','superseded'].includes(r.status))x.rejected++;else x.pending++;map.set(s,x)}return [...map.values()].sort((a,b)=>b.total-a.total)}
function renderBars(rows){const max=Math.max(1,...rows.map(x=>x.value));return `<div class="nr-bars">${rows.slice(0,10).map(x=>`<div class="nr-bar-row"><span>${esc(x.label)}</span><div class="nr-bar-track"><div class="nr-bar-fill" style="width:${Math.max(3,x.value/max*100)}%"></div></div><strong>${faNum(x.value)}</strong></div>`).join('')}</div>`}
function renderAnalytics(){const root=byId('nrAnalytics');if(!root)return;const pending=todayRows(),pub=todayHistory(['published_manual','published_auto']),rej=todayHistory(['rejected_manual','superseded']);const total=pub.length+rej.length;const rate=total?Math.round(pub.length/total*100):0;const superseded=todayHistory(['superseded']).length;const byCat=new Map();for(const r of [...pending,...pub,...rej]){const c=categoryOf(r);byCat.set(c,(byCat.get(c)||0)+1)}const cats=[...byCat].map(([label,value])=>({label,value})).sort((a,b)=>b.value-a.value);const sources=sourceStats();root.innerHTML=`<div class="nr-panel-grid"><article class="nr-metric"><span>بررسی‌شده امروز</span><strong>${faNum(total)}</strong></article><article class="nr-metric"><span>نرخ انتشار</span><strong>${total?faNum(rate)+'٪':'—'}</strong></article><article class="nr-metric"><span>تکراری/کنارگذاشته</span><strong>${faNum(superseded)}</strong></article><article class="nr-metric"><span>در انتظار</span><strong>${faNum(pending.length)}</strong></article></div><section class="nr-section"><h2>حجم خبر بر اساس موضوع</h2>${cats.length?renderBars(cats):'<div class="empty">داده کافی نیست.</div>'}</section><section class="nr-section"><h2>عملکرد منابع</h2>${sources.length?`<div style="overflow:auto"><table class="nr-table"><thead><tr><th>منبع</th><th>کل</th><th>منتشر</th><th>رد</th><th>در انتظار</th></tr></thead><tbody>${sources.slice(0,20).map(s=>`<tr><td>${esc(s.source)}</td><td>${faNum(s.total)}</td><td>${faNum(s.published)}</td><td>${faNum(s.rejected)}</td><td>${faNum(s.pending)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">داده کافی نیست.</div>'}</section>`}

async function loadNewsroomSettings(){try{const r=await fetch(`${RAW}/data/newsroom_settings.json?_=${Date.now()}`,{cache:'no-store'});if(r.ok){const got=await r.json();if(got&&typeof got==='object')newsroomSettings={...DEFAULT_SETTINGS,...got,market:{...DEFAULT_SETTINGS.market,...(got.market||{})},alerts:{...DEFAULT_SETTINGS.alerts,...(got.alerts||{})},ui:{...DEFAULT_SETTINGS.ui,...(got.ui||{})},sources:{...(got.sources||{})}}}}catch{}renderSettings();applyUiSettings()}
function settingRow(label,key,input,help=''){return `<div class="nr-setting-row"><label>${label}${help?`<small>${help}</small>`:''}</label>${input}</div>`}
function toggleInput(key,checked){return `<label class="nr-switch"><input type="checkbox" data-setting="${key}" ${checked?'checked':''}><span>${checked?'روشن':'خاموش'}</span></label>`}
function renderSettings(){const root=byId('nrSettings');if(!root)return;const s=newsroomSettings;const sources=sourceStats().slice(0,30);root.innerHTML=`<div class="nr-settings-grid"><section class="nr-setting-group nr-emergency"><h3>کنترل اضطراری</h3>${settingRow('قفل اضطراری','emergency_lock',toggleInput('emergency_lock',!!s.emergency_lock),'جمع‌آوری ادامه پیدا کند ولی انتشار خودکار متوقف شود.')}${settingRow('انتشار خودکار','auto_publish',toggleInput('auto_publish',!!s.auto_publish),'کلید اصلی رفتار انتشار خودکار.')}</section><section class="nr-setting-group"><h3>تازگی و تکرار</h3>${settingRow('حد تازگی خبر','freshness_hours',`<select class="field" data-setting="freshness_hours"><option value="1" ${s.freshness_hours==1?'selected':''}>۱ ساعت</option><option value="3" ${s.freshness_hours==3?'selected':''}>۳ ساعت</option><option value="6" ${s.freshness_hours==6?'selected':''}>۶ ساعت</option><option value="12" ${s.freshness_hours==12?'selected':''}>۱۲ ساعت</option></select>`)}${settingRow('حساسیت تکراری','dedup_mode',`<select class="field" data-setting="dedup_mode"><option value="strict" ${s.dedup_mode==='strict'?'selected':''}>سخت‌گیر</option><option value="balanced" ${s.dedup_mode==='balanced'?'selected':''}>متعادل</option><option value="loose" ${s.dedup_mode==='loose'?'selected':''}>آزادتر</option></select>`)}</section><section class="nr-setting-group"><h3>زلزله و نوتام</h3>${settingRow('حد ورود زلزله','earthquake_min',`<input class="field" type="number" step="0.1" min="0" max="10" data-setting="earthquake_min" value="${esc(s.earthquake_min)}">`)}${settingRow('حد فوری زلزله','earthquake_breaking',`<input class="field" type="number" step="0.1" min="0" max="10" data-setting="earthquake_breaking" value="${esc(s.earthquake_breaking)}">`)}${settingRow('حساسیت نوتام','notam_sensitivity',`<select class="field" data-setting="notam_sensitivity"><option value="high" ${s.notam_sensitivity==='high'?'selected':''}>زیاد</option><option value="normal" ${s.notam_sensitivity==='normal'?'selected':''}>عادی</option><option value="critical" ${s.notam_sensitivity==='critical'?'selected':''}>فقط بحرانی</option></select>`)}</section><section class="nr-setting-group"><h3>نمایش و هشدار</h3>${settingRow('تراکم پنل','ui.density',`<select class="field" data-setting="ui.density"><option value="comfortable" ${s.ui?.density==='comfortable'?'selected':''}>راحت</option><option value="compact" ${s.ui?.density==='compact'?'selected':''}>فشرده</option></select>`)}${settingRow('نمایش متن اصلی','ui.show_original',toggleInput('ui.show_original',!!s.ui?.show_original),'در حالت عادی فارسی اولویت دارد.')}${settingRow('صدای خبر فوری','alerts.breaking_sound',toggleInput('alerts.breaking_sound',!!s.alerts?.breaking_sound))}</section><section class="nr-setting-group" style="grid-column:1/-1"><h3>منابع دیده‌شده در پنل</h3>${sources.length?`<div class="nr-source-list">${sources.map(src=>{const pref=s.sources?.[src.source]||{};return `<div class="nr-source-item"><strong>${esc(src.source)}</strong><select class="field" data-source-enabled="${esc(src.source)}"><option value="true" ${pref.enabled!==false?'selected':''}>فعال</option><option value="false" ${pref.enabled===false?'selected':''}>غیرفعال</option></select><input class="field nr-trust" type="number" min="0" max="100" value="${Number(pref.trust??80)}" data-source-trust="${esc(src.source)}" title="امتیاز اعتماد"></div>`}).join('')}</div>`:'<div class="empty">هنوز منبعی برای تنظیم دیده نشده.</div>'}</section></div><div class="nr-settings-actions"><button class="btn green" id="nrSaveSettings">ذخیره تنظیمات</button><button class="btn ghost" id="nrReloadSettings">بازخوانی</button></div>`;byId('nrSaveSettings')?.addEventListener('click',saveSettings);byId('nrReloadSettings')?.addEventListener('click',loadNewsroomSettings);qsa('[data-setting][type="checkbox"]',root).forEach(x=>x.addEventListener('change',()=>x.parentElement.querySelector('span').textContent=x.checked?'روشن':'خاموش'))}
function assignPath(obj,path,value){const parts=path.split('.');let cur=obj;for(let i=0;i<parts.length-1;i++){cur[parts[i]]=cur[parts[i]]||{};cur=cur[parts[i]]}cur[parts.at(-1)]=value}
function collectSettings(){const next=JSON.parse(JSON.stringify(newsroomSettings));qsa('#nrSettings [data-setting]').forEach(el=>{let v;if(el.type==='checkbox')v=el.checked;else if(el.type==='number')v=Number(el.value);else v=el.value;assignPath(next,el.dataset.setting,v)});next.sources=next.sources||{};qsa('#nrSettings [data-source-enabled]').forEach(el=>{const k=el.dataset.sourceEnabled;next.sources[k]=next.sources[k]||{};next.sources[k].enabled=el.value==='true'});qsa('#nrSettings [data-source-trust]').forEach(el=>{const k=el.dataset.sourceTrust;next.sources[k]=next.sources[k]||{};next.sources[k].trust=Math.max(0,Math.min(100,Number(el.value)||0))});return next}
async function saveSettings(){if(!requireConnection({type:'settings'}))return;const next=collectSettings();try{const id=await createCommand({action:'settings_save',item_id:'',settings:next,title:'',body:''});toast('در حال ذخیره تنظیمات…');const result=await pollCommandResult(id,120000);if(result.status==='failed')throw Error(result.message||'ذخیره ناموفق بود');newsroomSettings=next;applyUiSettings();toast('تنظیمات اتاق خبر ذخیره شد')}catch(e){toast('ذخیره تنظیمات انجام نشد: '+e.message,12000)}}
function applyUiSettings(){document.documentElement.dataset.nrDensity=newsroomSettings.ui?.density||'comfortable';document.body.classList.toggle('nr-emergency-on',!!newsroomSettings.emergency_lock)}

function keyboard(e){if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;if(e.key.toLowerCase()==='f'){e.preventDefault();byId('refreshBtn')?.click();return}if(e.key.toLowerCase()==='p'&&activeCardId){e.preventDefault();openPreview(activeCardId);return}const cards=qsa('#queueList .card');if(!cards.length)return;let idx=Math.max(0,cards.findIndex(c=>c.dataset.id===activeCardId));if(e.key.toLowerCase()==='j')idx=Math.min(cards.length-1,idx+1);else if(e.key.toLowerCase()==='k')idx=Math.max(0,idx-1);else return;activeCardId=cards[idx].dataset.id;cards[idx].scrollIntoView({behavior:'smooth',block:'center'});cards[idx].style.outline='2px solid rgba(101,170,255,.45)';setTimeout(()=>cards[idx].style.outline='',500)}

function init(){ensureShell();ensureTabsAndViews();syncListTools();modal();byId('clearCurrentView')?.addEventListener('click',()=>clearView(false));byId('clearFilteredView')?.addEventListener('click',()=>clearView(true));document.addEventListener('keydown',keyboard);const obs=new MutationObserver(()=>{decorateCards();renderSituation()});const list=byId('queueList');if(list)obs.observe(list,{childList:true,subtree:true});decorateCards();renderSituation();renderAnalytics();loadNewsroomSettings();setInterval(()=>{decorateCards();renderSituation();if(activeView()==='analytics')renderAnalytics()},5000);window.NewsroomV1={localSource,categoryOf,priorityOf,renderAnalytics,renderSituation,clearView,openPreview,loadNewsroomSettings}}

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
