(() => {
  if (!document.getElementById('liveFeed')) return;
  const UI = window.BikhabarUI || {};
  const feed = document.getElementById('liveFeed');
  const actionState = document.getElementById('actionState');
  const scanNow = document.getElementById('scanNow');
  const publishingToggle = document.getElementById('publishingToggle');
  const liveSelectAll = document.getElementById('liveSelectAll');
  const liveBulkDelete = document.getElementById('liveBulkDelete');
  const clearCurrentFeed = document.getElementById('clearCurrentFeed');
  const liveBulkState = document.getElementById('liveBulkState');

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
        if (card) storyProgress(card, result.status === 'queued' ? 'در صف لونا…' : 'لونا در حال آماده‌سازی نسخه نهایی…');
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

  window.BikhabarActions = {requestJSON, pollCommand, storyProgress};

  async function publishCard(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    card.classList.add('is-busy');
    storyProgress(card, 'در حال ارسال خبر به لونا…');
    try {
      const queued = await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/publish`, {method:'POST'});
      storyProgress(card, 'در صف لونا…');
      const result = await pollCommand(queued.command_id, {card});
      storyProgress(card, `منتشر شد · Message ID ${result.telegram_message_id || 'ثبت شد'}`, 'success');
      UI.toast?.('نسخه نهایی لونا منتشر شد.', 'success');
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
    if (!id || card.classList.contains('is-busy')) return;
    card.classList.add('is-busy');
    storyProgress(card, 'در حال رد خبر…');
    try {
      await requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/reject`, {method:'POST'});
      card.remove();
      syncBulkControls();
      UI.toast?.('خبر رد شد.', 'success');
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      card.classList.remove('is-busy');
      storyProgress(card, error.message, 'error');
      UI.toast?.(error.message, 'error');
    }
  }

  function liveCheckboxes() {
    return [...feed.querySelectorAll('.live-select')];
  }

  function selectedLiveIds() {
    return liveCheckboxes().filter(box => box.checked).map(box => String(box.value || '')).filter(Boolean);
  }

  function syncBulkControls() {
    const boxes = liveCheckboxes();
    const selected = boxes.filter(box => box.checked).length;
    if (liveBulkDelete) liveBulkDelete.disabled = selected === 0;
    if (liveSelectAll) {
      liveSelectAll.checked = boxes.length > 0 && selected === boxes.length;
      liveSelectAll.indeterminate = selected > 0 && selected < boxes.length;
    }
    if (liveBulkState) liveBulkState.textContent = selected ? `${selected.toLocaleString('fa-IR')} خبر انتخاب شده · فقط از پنل` : 'فقط از پنل؛ هیچ پیامی در تلگرام حذف نمی‌شود.';
  }

  async function clearLiveIds(ids, label) {
    if (!ids.length) return;
    const accepted = await UI.confirmAction?.({
      title: label,
      text: 'این کار فقط آیتم‌های انتخاب‌شده را از فید پنل پاک می‌کند و هیچ پیام تلگرامی حذف نمی‌شود.',
      accept: 'حذف از پنل',
    });
    if (!accepted) return;
    if (liveBulkDelete) liveBulkDelete.disabled = true;
    if (clearCurrentFeed) clearCurrentFeed.disabled = true;
    try {
      const result = await requestJSON('/api/command-center/clear', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scope:'live', ids}),
      });
      UI.toast?.(result.message || 'از پنل پاک شد.', 'success');
      window.dispatchEvent(new Event('newsroom:refresh'));
    } catch (error) {
      UI.toast?.(error.message, 'error');
    } finally {
      if (clearCurrentFeed) clearCurrentFeed.disabled = false;
      syncBulkControls();
    }
  }

  feed.addEventListener('change', event => {
    if (event.target.matches('.live-select')) syncBulkControls();
  });

  liveSelectAll?.addEventListener('change', () => {
    liveCheckboxes().forEach(box => { box.checked = liveSelectAll.checked; });
    syncBulkControls();
  });
  liveBulkDelete?.addEventListener('click', () => clearLiveIds(selectedLiveIds(), 'خبرهای انتخاب‌شده از پنل پاک شوند؟'));
  clearCurrentFeed?.addEventListener('click', () => {
    const ids = [...feed.querySelectorAll('[data-story-id]')].map(card => card.dataset.storyId).filter(Boolean);
    clearLiveIds(ids, 'کل ورودی فعلی پنل پاک شود؟');
  });

  feed.addEventListener('click', event => {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    const action = target.dataset.action;
    if (action === 'source' || action === 'edit' || action === 'retry-localization') return;
    event.preventDefault();
    const card = target.closest('[data-story-id]');
    if (action === 'publish') void publishCard(card);
    if (action === 'reject') void rejectCard(card);
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
    publishingToggle.textContent = active ? '⛔ توقف کامل انتشار' : 'فعال‌کردن انتشار';
    publishingToggle.classList.toggle('nr-button-danger', active);
    publishingToggle.classList.toggle('nr-button-primary', !active);
  }
  window.addEventListener('newsroom:snapshot', event => {
    syncPublishing(event.detail);
    syncBulkControls();
  });

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

  function previewText(value) {
    return String(value || '')
      .replace(/<a\b[^>]*>(.*?)<\/a>/gi, '$1')
      .replace(/<\/?(?:b|strong|i|em|u|s|code|pre)>/gi, '')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  }

  function renderModulePreview(panel, preview) {
    if (!panel) return;
    panel.replaceChildren();
    if (preview.image_url) {
      const image = document.createElement('img');
      image.className = 'module-preview-image';
      image.alt = 'پیش‌نمایش گزارش';
      image.loading = 'eager';
      image.src = `${preview.image_url}?t=${encodeURIComponent(preview.generated_at || Date.now())}`;
      panel.appendChild(image);
    }
    const message = previewText(preview.message || preview.text || preview.caption || '');
    if (message) {
      const pre = document.createElement('pre');
      pre.textContent = message;
      panel.appendChild(pre);
    }
    if (preview.available_for_publish === false) {
      const warning = document.createElement('small');
      warning.className = 'preview-warning';
      warning.textContent = 'داده برای مشاهده موجود است، اما برای انتشار هنوز کافی نیست.';
      panel.appendChild(warning);
    }
    if (preview.generated_at) {
      const time = document.createElement('small');
      time.textContent = `به‌روزرسانی: ${UI.relativeTime ? UI.relativeTime(preview.generated_at) : preview.generated_at}`;
      panel.appendChild(time);
    }
    if (!panel.childNodes.length) panel.textContent = 'داده واقعی کافی برای پیش‌نمایش موجود نیست.';
    panel.hidden = false;
  }

  async function loadModulePreview(moduleName, panel) {
    let preview = await requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`);
    const hasCached = Boolean(preview.available && (preview.message || preview.text || preview.caption || preview.image_url));
    if (hasCached) {
      renderModulePreview(panel, preview);
      return preview;
    }

    if (panel) {
      panel.textContent = 'در حال ساخت پیش‌نمایش واقعی…';
      panel.hidden = false;
    }
    const queued = await requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`, {method:'POST'});
    if (queued.command_id) {
      const result = await pollCommand(queued.command_id, {timeoutMs:45000});
      if (!result || result.status === 'failed') throw new Error(result?.message || 'ساخت پیش‌نمایش ناموفق بود.');
    }
    preview = await requestJSON(`/api/command-center/module/${encodeURIComponent(moduleName)}/preview`);
    renderModulePreview(panel, preview);
    return preview;
  }

  document.addEventListener('click', async event => {
    const previewButton = event.target.closest('[data-module-preview]');
    const runButton = event.target.closest('[data-module-run]');
    if (!previewButton && !runButton) return;
    const button = previewButton || runButton;
    const moduleName = previewButton?.dataset.modulePreview || runButton?.dataset.moduleRun;
    if (!moduleName) return;
    const panel = document.querySelector(`[data-preview-panel="${CSS.escape(moduleName)}"]`) || document.querySelector(`[data-preview="${CSS.escape(moduleName)}"]`);
    if (previewButton && panel && !panel.hidden) {
      panel.hidden = true;
      return;
    }
    button.disabled = true;
    try {
      if (previewButton) {
        await loadModulePreview(moduleName, panel);
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

  syncBulkControls();
})();