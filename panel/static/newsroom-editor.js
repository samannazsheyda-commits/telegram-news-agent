(() => {
  const sheet = document.getElementById('editorSheet');
  const feed = document.getElementById('liveFeed');
  if (!sheet || !feed) return;

  const UI = window.BikhabarUI || {};
  const Actions = window.BikhabarActions || {};
  const storyId = document.getElementById('editorStoryId');
  const title = document.getElementById('editorTitle');
  const body = document.getElementById('editorBody');
  const source = document.getElementById('editorSource');
  const save = document.getElementById('editorSave');
  const publish = document.getElementById('editorPublish');
  let activeCard = null;

  function closeEditor() {
    sheet.hidden = true;
    document.body.style.overflow = '';
    activeCard = null;
  }

  function openEditor(card) {
    if (!card) return;
    activeCard = card;
    storyId.value = card.dataset.storyId || '';
    title.value = card.dataset.storyTitle || card.querySelector('h3')?.textContent?.trim() || '';
    body.value = card.dataset.storyBody || card.querySelector('p')?.textContent?.trim() || '';
    source.textContent = card.dataset.storySource || 'منبع';
    sheet.hidden = false;
    document.body.style.overflow = 'hidden';
    window.setTimeout(() => title.focus(), 0);
  }

  function payload() {
    return {title: title.value.trim(), body: body.value.trim()};
  }

  function validateCopy(copy) {
    if (!copy.title) throw new Error('تیتر فارسی نمی‌تواند خالی باشد.');
    if (copy.title.length > 280 || copy.body.length > 4000) throw new Error('متن ویرایش از حد مجاز طولانی‌تر است.');
    return copy;
  }

  function syncCard(copy) {
    if (!activeCard) return;
    activeCard.dataset.storyTitle = copy.title;
    activeCard.dataset.storyBody = copy.body;
    const heading = activeCard.querySelector('h3');
    if (heading) heading.textContent = copy.title;
    let paragraph = activeCard.querySelector('p');
    if (copy.body) {
      if (!paragraph) {
        paragraph = document.createElement('p');
        activeCard.querySelector('.nr-story-actions')?.before(paragraph);
      }
      paragraph.textContent = copy.body;
    } else if (paragraph) {
      paragraph.remove();
    }
  }

  async function sendEditor(action) {
    if (!Actions.requestJSON) throw new Error('مسیر عملیات پنل آماده نیست.');
    const id = storyId.value;
    if (!id) throw new Error('شناسه خبر معتبر نیست.');
    const copy = validateCopy(payload());
    return {
      copy,
      result: await Actions.requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/${action}`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(copy),
      }),
    };
  }

  feed.addEventListener('click', event => {
    const button = event.target.closest('[data-action="edit"]');
    if (!button) return;
    event.preventDefault();
    openEditor(button.closest('[data-story-id]'));
  });

  sheet.querySelectorAll('[data-editor-close]').forEach(node => node.addEventListener('click', closeEditor));
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !sheet.hidden) closeEditor();
  });

  save?.addEventListener('click', async () => {
    save.disabled = true;
    if (publish) publish.disabled = true;
    try {
      const {copy, result} = await sendEditor('review');
      syncCard(copy);
      UI.toast?.(result.message || 'نسخه ویرایش‌شده ذخیره شد.', 'success');
      closeEditor();
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      UI.toast?.(error.message, 'error');
    } finally {
      save.disabled = false;
      if (publish) publish.disabled = false;
    }
  });

  publish?.addEventListener('click', async () => {
    let copy;
    try { copy = validateCopy(payload()); }
    catch (error) { UI.toast?.(error.message, 'error'); return; }

    const accepted = await UI.confirmAction?.({
      title:'نسخه ویرایش‌شده منتشر شود؟',
      text:`${copy.title}\n\nنتیجه فقط بعد از تأیید runtime موفق اعلام می‌شود.`,
      accept:'انتشار نسخه نهایی',
    });
    if (!accepted) return;

    publish.disabled = true;
    if (save) save.disabled = true;
    const card = activeCard;
    try {
      const sent = await sendEditor('publish');
      syncCard(sent.copy);
      if (card) Actions.storyProgress?.(card, 'در صف انتشار V3…');
      const result = sent.result.command_id
        ? await Actions.pollCommand(sent.result.command_id, {card, timeoutMs:45000})
        : sent.result;
      if (card) Actions.storyProgress?.(card, `انجام شد · Message ID ${result.telegram_message_id || 'ثبت شد'}`, 'success');
      UI.toast?.('نسخه ویرایش‌شده با تأیید V3 منتشر شد.', 'success');
      closeEditor();
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      if (card) Actions.storyProgress?.(card, error.message, error.ambiguous ? 'warn' : 'error');
      UI.toast?.(error.message, error.ambiguous ? 'warn' : 'error');
    } finally {
      publish.disabled = false;
      if (save) save.disabled = false;
    }
  });
})();
