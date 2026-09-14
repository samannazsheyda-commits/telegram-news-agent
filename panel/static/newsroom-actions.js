(() => {
  if (!document.getElementById('liveFeed')) return;
  const UI = window.BikhabarUI || {};
  const feed = document.getElementById('liveFeed');
  const actionState = document.getElementById('actionState');
  const scanNow = document.getElementById('scanNow');
  const publishingToggle = document.getElementById('publishingToggle');

  async function requestJSON(url, options = {}) {
    const headers = UI.csrfHeaders ? UI.csrfHeaders(options.headers || {}) : (options.headers || {});
    const response = await fetch(url, {credentials:'same-origin', cache:'no-store', ...options, headers});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      const error = new Error(data.message || data.error || `HTTP ${response.status}`);
      error.payload = data;
      throw error;
    }
    return data;
  }

  function setActionState(text, bad = false) {
    if (!actionState) return;
    actionState.textContent = text;
    actionState.classList.toggle('nr-state-bad', bad);
  }

  function storyProgress(card, text, kind = '') {
    const progress = card?.querySelector('.nr-story-progress');
    if (!progress) return;
    progress.hidden = !text;
    progress.textContent = text || '';
    progress.className = `nr-story-progress ${kind}`.trim();
  }

  async function pollCommand(commandId, {card = null, timeoutMs = 45000} = {}) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const result = await requestJSON(`/api/newsroom/command/${encodeURIComponent(commandId)}`);
      if (result.status === 'queued' || result.status === 'processing') {
        if (card) storyProgress(card, result.status === 'queued' ? 'در صف انتشار V3…' : 'در حال انتشار V3…');
        await new Promise(resolve => window.setTimeout(resolve, 900));
        continue;
      }
      if (result.status === 'succeeded' || result.status === 'reconciled') return result;
      if (result.status === 'ambiguous') {
        const error = new Error(result.message || 'وضعیت ارسال نامشخص است؛ دوباره منتشر نکن.');
        error.ambiguous = true;
        throw error;
      }
      throw new Error(result.message || result.error || 'فرمان ناموفق بود.');
    }
    throw new Error('پاسخ runtime دیرتر از حد انتظار شد؛ وضعیت را دوباره بررسی کن.');
  }

  async function publishCard(card) {
    const id = card?.dataset.storyId;
    if (!id) return;
    const title = card.dataset.storyTitle || card.querySelector('h3')?.textContent || 'این خبر';
    const source = card.dataset.storySource || 'منبع خبر';
    const accepted = await UI.confirmAction?.({
      title: 'انتشار در تلگرام؟',
      text: `${title}\n\nمنبع: ${source}\nنتیجه فقط بعد از تأیید runtime موفق اعلام می‌شود.`,
      accept: 'انتشار خبر',
    });
    if (!accepted) return;
    card.classList.add('is-busy');
    storyProgress(card, 'در حال ارسال فرمان…');
    try {
      const queued = await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/publish`, {method:'POST'});
      storyProgress(card, 'در صف انتشار V3…');
      const result = await pollCommand(queued.command_id, {card});
      storyProgress(card, `انجام شد · Message ID ${result.telegram_message_id || 'ثبت شد'}`, 'success');
      UI.toast?.('خبر با تأیید V3 منتشر شد.', 'success');
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      storyProgress(card, error.message, error.ambiguous ? 'warn' : 'error');
      UI.toast?.(error.message, error.ambiguous ? 'warn' : 'error');
    } finally {
      card.classList.remove('is-busy');
    }
  }

  async function rejectCard(card) {
    const id = card?.dataset.storyId;
    if (!id) return;
    const accepted = await UI.confirmAction?.({title:'رد این خبر؟', text:'خبر از صف اقدام سردبیری کنار می‌رود. چیزی از تلگرام حذف نمی‌شود.', accept:'رد خبر'});
    if (!accepted) return;
    card.classList.add('is-busy');
    try {
      await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/reject`, {method:'POST'});
      card.remove();
      UI.toast?.('خبر رد شد.', 'success');
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      card.classList.remove('is-busy');
      UI.toast?.(error.message, 'error');
    }
  }

  feed.addEventListener('click', event => {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    const action = target.dataset.action;
    if (action === 'source' || action === 'edit') return;
    event.preventDefault();
    const card = target.closest('[data-story-id]');
    if (action === 'publish') publishCard(card);
    if (action === 'reject') rejectCard(card);
  });

  scanNow?.addEventListener('click', async () => {
    scanNow.disabled = true;
    setActionState('در حال ارسال فرمان اسکن…');
    try {
      const result = await requestJSON('/api/newsroom/scan', {method:'POST'});
      setActionState('اسکن در صف runtime است');
      if (result.command_id) {
        const done = await pollCommand(result.command_id, {timeoutMs:30000});
        setActionState(done.message || 'اسکن انجام شد');
      }
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      setActionState(error.message, true);
      UI.toast?.(error.message, 'error');
    } finally { scanNow.disabled = false; }
  });

  function syncPublishing(snapshot) {
    if (!publishingToggle || !snapshot) return;
    const active = Boolean(snapshot.publishing);
    publishingToggle.dataset.enabled = active ? '1' : '0';
    publishingToggle.textContent = active ? 'توقف انتشار' : 'فعال‌کردن انتشار';
    publishingToggle.classList.toggle('nr-button-danger', active);
    publishingToggle.classList.toggle('nr-button-primary', !active);
  }
  window.addEventListener('newsroom:snapshot', event => syncPublishing(event.detail));

  publishingToggle?.addEventListener('click', async () => {
    const currentlyEnabled = publishingToggle.dataset.enabled !== '0';
    const nextEnabled = !currentlyEnabled;
    const accepted = await UI.confirmAction?.({
      title: nextEnabled ? 'انتشار دوباره فعال شود؟' : 'انتشار کامل متوقف شود؟',
      text: nextEnabled ? 'V3 دوباره اجازه انتشار خبر خواهد داشت.' : 'تا زمان فعال‌کردن دوباره، انتشار خودکار متوقف می‌ماند.',
      accept: nextEnabled ? 'فعال کن' : 'متوقف کن',
    });
    if (!accepted) return;
    publishingToggle.disabled = true;
    try {
      const result = await requestJSON('/api/newsroom/publishing', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:nextEnabled}),
      });
      UI.toast?.(result.message, 'success');
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) { UI.toast?.(error.message, 'error'); }
    finally { publishingToggle.disabled = false; }
  });

  document.addEventListener('click', async event => {
    const previewButton = event.target.closest('[data-module-preview]');
    const runButton = event.target.closest('[data-module-run]');
    if (!previewButton && !runButton) return;
    const button = previewButton || runButton;
    const moduleName = previewButton?.dataset.modulePreview || runButton?.dataset.moduleRun;
    if (!moduleName) return;
    button.disabled = true;
    try {
      if (previewButton) {
        const queued = await requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`, {method:'POST'});
        if (queued.command_id) await pollCommand(queued.command_id, {timeoutMs:45000});
        const preview = await requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`);
        const panel = document.querySelector(`[data-preview="${CSS.escape(moduleName)}"]`);
        if (panel) { panel.textContent = preview.message || 'پیش‌نمایش آماده است.'; panel.hidden = false; }
      } else {
        const accepted = await UI.confirmAction?.({title:'انتشار گزارش ویژه؟', text:'این فرمان می‌تواند یک پیام واقعی در تلگرام منتشر کند.', accept:'انتشار'});
        if (!accepted) return;
        const queued = await requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}`, {method:'POST'});
        if (queued.command_id) await pollCommand(queued.command_id, {timeoutMs:60000});
        UI.toast?.('گزارش ویژه منتشر شد.', 'success');
      }
    } catch (error) { UI.toast?.(error.message, error.ambiguous ? 'warn' : 'error'); }
    finally { button.disabled = false; }
  });
})();
