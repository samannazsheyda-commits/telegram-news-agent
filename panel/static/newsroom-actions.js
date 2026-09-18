(() => {
  const feed = document.getElementById('liveFeed');
  if (!feed) return;

  const UI = window.BikhabarUI || {};
  const scanNow = document.getElementById('scanNow');
  const publishingToggle = document.getElementById('publishingToggle');
  const dailyInput = document.getElementById('dailyLimitInput');
  const saveDailyLimit = document.getElementById('saveDailyLimit');
  const limitSaveState = document.getElementById('limitSaveState');

  async function requestJSON(url, options = {}) {
    const headers = UI.csrfHeaders ? UI.csrfHeaders(options.headers || {}) : (options.headers || {});
    const response = await fetch(url, {credentials:'same-origin', cache:'no-store', ...options, headers});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.message || data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  function progress(card, text, kind = '') {
    const node = card?.querySelector('.v4-story-progress');
    if (!node) return;
    node.textContent = text || '';
    node.className = `v4-story-progress ${kind}`.trim();
  }

  function setBusy(card, value) {
    if (!card) return;
    card.classList.toggle('is-busy', Boolean(value));
    card.querySelectorAll('button').forEach(button => {
      if (button.dataset.action !== 'machine') button.disabled = Boolean(value) || (button.dataset.action === 'publish-prepared' && !window.BikhabarV4?.getLuna(card.dataset.storyId));
    });
  }

  async function poll(commandId, card, actionLabel) {
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {
      const result = await requestJSON(`/api/newsroom/v4/command/${encodeURIComponent(commandId)}`);
      if (result.status === 'queued' || result.status === 'processing') {
        progress(card, actionLabel);
        await new Promise(resolve => window.setTimeout(resolve, 850));
        continue;
      }
      if (result.status === 'succeeded' || result.status === 'reconciled') return result;
      if (result.status === 'ambiguous') throw new Error('وضعیت ارسال نامشخص است؛ دوباره منتشر نکن.');
      throw new Error(result.message || result.error || 'عملیات ناموفق بود.');
    }
    throw new Error('پاسخ سیستم دیرتر از حد انتظار شد.');
  }

  async function prepareWithLuna(card) {
    const id = String(card?.dataset.storyId || '');
    if (!id || card.classList.contains('is-busy')) return;
    setBusy(card, true);
    progress(card, 'لونا در حال ترجمه و ویراستاری است…');
    try {
      const queued = await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/luna`, {method:'POST'});
      const result = await poll(queued.command_id, card, 'لونا در حال آماده‌سازی نسخه نهایی…');
      if (!result.title) throw new Error('نسخه لونا خالی برگشت.');
      window.BikhabarV4?.setLuna(id, result.title, result.body || '');
      window.dispatchEvent(new CustomEvent('newsroom:luna-ready', {detail:{id, title:result.title, body:result.body || ''}}));
      progress(card, 'نسخه لونا آماده است؛ متن را ببین و اگر تأیید بود منتشر کن.', 'success');
      UI.toast?.('نسخه لونا آماده شد؛ هنوز منتشر نشده.', 'success');
    } catch (error) {
      progress(card, error.message, 'error');
      UI.toast?.(error.message, 'error');
    } finally {
      setBusy(card, false);
    }
  }

  async function publishPrepared(card) {
    const id = String(card?.dataset.storyId || '');
    const luna = window.BikhabarV4?.getLuna(id);
    if (!id || !luna || card.classList.contains('is-busy')) return;
    const accepted = await UI.confirmAction?.({
      title: 'نسخه دیده‌شده لونا منتشر شود؟',
      text: 'همین متن لونا در کانال بی‌خبر منتشر می‌شود.',
      accept: 'انتشار',
    });
    if (accepted === false) return;
    setBusy(card, true);
    progress(card, 'در حال انتشار نسخه تأییدشده…');
    try {
      const queued = await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/publish-prepared`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({title:luna.title, body:luna.body || ''}),
      });
      const result = await poll(queued.command_id, card, 'در حال ارسال امن به تلگرام…');
      progress(card, `منتشر شد${result.telegram_message_id ? ` · ${result.telegram_message_id}` : ''}`, 'success');
      UI.toast?.('خبر منتشر شد.', 'success');
      window.dispatchEvent(new CustomEvent('newsroom:story-published', {detail:{id}}));
    } catch (error) {
      progress(card, error.message, 'error');
      UI.toast?.(error.message, 'error');
    } finally {
      setBusy(card, false);
    }
  }

  async function rejectStory(card) {
    const id = String(card?.dataset.storyId || '');
    if (!id || card.classList.contains('is-busy')) return;
    setBusy(card, true);
    progress(card, 'در حال رد خبر…');
    try {
      await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/reject`, {method:'POST'});
      window.dispatchEvent(new CustomEvent('newsroom:story-rejected', {detail:{id}}));
      UI.toast?.('خبر رد شد.', 'success');
    } catch (error) {
      progress(card, error.message, 'error');
      UI.toast?.(error.message, 'error');
      setBusy(card, false);
    }
  }

  feed.addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const card = button.closest('[data-story-id]');
    if (!card) return;
    const action = button.dataset.action;
    if (action === 'luna') {
      event.preventDefault();
      void prepareWithLuna(card);
    } else if (action === 'publish-prepared') {
      event.preventDefault();
      void publishPrepared(card);
    } else if (action === 'reject') {
      event.preventDefault();
      void rejectStory(card);
    }
  });

  scanNow?.addEventListener('click', async () => {
    if (scanNow.disabled) return;
    scanNow.disabled = true;
    const old = scanNow.textContent;
    scanNow.textContent = 'در حال اسکن…';
    try {
      await requestJSON('/api/newsroom/scan', {method:'POST'});
      UI.toast?.('اسکن فوری در صف اجرا قرار گرفت.', 'success');
      window.setTimeout(() => window.BikhabarV4?.refresh({force:true}), 1800);
    } catch (error) {
      UI.toast?.(error.message, 'error');
    } finally {
      scanNow.disabled = false;
      scanNow.textContent = old;
    }
  });

  window.addEventListener('newsroom:v4-status', event => {
    if (!publishingToggle) return;
    const active = Boolean(event.detail?.publishing);
    publishingToggle.dataset.enabled = active ? '1' : '0';
    publishingToggle.textContent = active ? 'توقف انتشار خودکار' : 'فعال‌کردن انتشار خودکار';
    publishingToggle.classList.toggle('v4-btn-danger', active);
    publishingToggle.classList.toggle('v4-btn-primary', !active);
  });

  publishingToggle?.addEventListener('click', async () => {
    const active = publishingToggle.dataset.enabled !== '0';
    publishingToggle.disabled = true;
    try {
      const result = await requestJSON('/api/newsroom/publishing', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:!active}),
      });
      UI.toast?.(result.message || 'تنظیم شد.', 'success');
      window.BikhabarV4?.refresh({force:true});
    } catch (error) {
      UI.toast?.(error.message, 'error');
    } finally {
      publishingToggle.disabled = false;
    }
  });

  saveDailyLimit?.addEventListener('click', async () => {
    const limit = Math.max(1, Math.min(100, Number(dailyInput?.value || 35)));
    saveDailyLimit.disabled = true;
    if (limitSaveState) limitSaveState.textContent = 'در حال ذخیره…';
    try {
      const result = await requestJSON('/api/newsroom/v4/daily-limit', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({daily_limit:limit, special_limit:5}),
      });
      if (dailyInput) dailyInput.value = result.daily_limit;
      if (limitSaveState) limitSaveState.textContent = 'ذخیره شد';
      UI.toast?.('سهمیه روزانه ذخیره شد.', 'success');
      window.BikhabarV4?.refresh({force:true});
    } catch (error) {
      if (limitSaveState) limitSaveState.textContent = error.message;
      UI.toast?.(error.message, 'error');
    } finally {
      saveDailyLimit.disabled = false;
      window.setTimeout(() => { if (limitSaveState) limitSaveState.textContent = ''; }, 2500);
    }
  });
})();
