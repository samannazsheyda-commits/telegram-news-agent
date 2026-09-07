(()=>{
'use strict';

const STORAGE_KEY='bikhabar_recent_published';
const TTL_MS=36*60*60*1000;
let pendingPublishId='';

function readRecent(){
  try{
    const raw=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
    const now=Date.now();
    const fresh={};
    for(const [id,ts] of Object.entries(raw||{})){
      const at=Number(ts)||0;
      if(id&&at&&now-at<TTL_MS)fresh[id]=at;
    }
    localStorage.setItem(STORAGE_KEY,JSON.stringify(fresh));
    return fresh;
  }catch{
    return {};
  }
}

function rememberPublished(id){
  if(!id)return;
  const recent=readRecent();
  recent[id]=Date.now();
  localStorage.setItem(STORAGE_KEY,JSON.stringify(recent));
}

function removeRememberedCards(){
  const recent=readRecent();
  document.querySelectorAll('#queueList .card[data-id]').forEach(card=>{
    if(recent[card.dataset.id])card.remove();
  });
}

document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action="publish"]');
  if(!button)return;
  const card=button.closest('.card[data-id]');
  pendingPublishId=card?.dataset.id||'';
},true);

const observer=new MutationObserver(()=>{
  const toastText=(document.getElementById('toastText')?.textContent||'').trim();
  if(pendingPublishId && (toastText.includes('انتشار در تلگرام تأیید شد') || toastText.includes('در تلگرام منتشر شد'))){
    rememberPublished(pendingPublishId);
    pendingPublishId='';
  }
  if(toastText.includes('انتشار ثبت نشد'))pendingPublishId='';
  removeRememberedCards();
});

observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true});
removeRememberedCards();
})();
