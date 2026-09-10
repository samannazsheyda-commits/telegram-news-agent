(() => {
  const feed = document.getElementById('liveFeed');
  const soundToggle = document.getElementById('soundToggle');
  const badge = document.getElementById('newNewsBadge');
  const publishingState = document.getElementById('publishingState');
  const panicToggle = document.getElementById('panicToggle');
  const commandResult = document.getElementById('commandResult');
  const liveCount = document.getElementById('liveCount');
  const queueCount = document.getElementById('queueCount');
  const liveSelectAll = document.getElementById('liveSelectAll');
  const liveBulkDelete = document.getElementById('liveBulkDelete');
  const liveBulkState = document.getElementById('liveBulkState');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (!feed || !soundToggle) return;

  let soundOn = localStorage.getItem('bikhabar_sound_alert') !== 'off';
  let firstId = feed.querySelector('[data-news-id]')?.dataset.newsId || '';
  let audioContext = null;
  let publishingEnabled = true;
  let latestItems = [];
  const commandWatchers = new Map();
  const localizedCache = new Map();
  const localizationInFlight = new Set();

  function faTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit', year: 'numeric', month: 'short', day: 'numeric' });
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function paintSound() {
    soundToggle.setAttribute('aria-pressed', soundOn ? 'true' : 'false');
    soundToggle.textContent = soundOn ? '🔔 صدا روشن' : '🔕 صدا خاموش';
  }

  function beep() {
    if (!soundOn) return;
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioContext.createOscillator();
      const gain = audioContext.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(980, audioContext.currentTime);
      gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, audioContext.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.16);
      osc.connect(gain); gain.connect(audioContext.destination);
      osc.start(); osc.stop(audioContext.currentTime + 0.18);
    } catch (_) {}
  }

  function showBadge() {
    if (!badge) return;
    badge.hidden = false;
    window.clearTimeout(showBadge.timer);
    showBadge.timer = window.setTimeout(() => { badge.hidden = true; }, 3500);
  }

  function paintPublishing() {
    if (publishingState) publishingState.textContent = publishingEnabled ? 'فعال' : 'متوقف';
    if (panicToggle) panicToggle.textContent = publishingEnabled ? '⛔ توقف کامل انتشار' : '▶️ ازسرگیری انتشار';
  }

  function selectedIds() {
    return Array.from(feed.querySelectorAll('.live-select:checked')).map(input => input.value).filter(Boolean);
  }

  function syncBulkState() {
    const boxes = Array.from(feed.querySelectorAll('.live-select'));
    const selected = boxes.filter(box => box.checked).length;
    if (liveBulkDelete) liveBulkDelete.disabled = selected === 0;
    if (liveSelectAll) liveSelectAll.checked = boxes.length > 0 && selected === boxes.length;
    if (liveBulkState) liveBulkState.textContent = selected ? `${selected.toLocaleString('fa-IR')} خبر انتخاب شده` : '';
  }

  async function getJson(url) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async function postJson(url, payload = {}) {
    const response = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async function watchCommand(commandId, label = 'فرمان') {
    if (!commandId || commandWatchers.has(commandId)) return null;
    commandWatchers.set(commandId, true);
    const started = Date.now();
    while (Date.now() - started < 45000) {
      try {
        const data = await getJson(`/api/command-center/command/${encodeURIComponent(commandId)}`);
        if (commandResult) commandResult.textContent = `${label}: ${data.message || data.status}`;
        if (['succeeded', 'failed', 'reconciled'].includes(data.status)) {
          commandWatchers.delete(commandId);
          await Promise.allSettled([refreshStatus(), refreshHealth(), refreshLiveFeed()]);
          return data;
        }
      } catch (_) {}
      await new Promise(resolve => setTimeout(resolve, 650));
    }
    commandWatchers.delete(commandId);
    if (commandResult) commandResult.textContent = `${label}: نتیجه هنوز از ایجنت نرسیده`;
    return null;
  }

  function mergeLocalized(item) {
    const id = String(item.id || item.item_id || '');
    const localized = localizedCache.get(id);
    return localized ? { ...item, ...localized, needs_localization: false } : item;
  }

  function renderLatest() {
    renderFeed(latestItems.map(mergeLocalized));
  }

  async function localizeIds(ids) {
    const unique = [...new Set(ids.filter(Boolean))].slice(0, 12);
    if (!unique.length) return [];
    const data = await postJson('/api/live-feed/localize', { ids: unique });
    const rows = Array.isArray(data.items) ? data.items : [];
    for (const item of rows) {
      const id = String(item.id || item.item_id || '');
      if (id) localizedCache.set(id, item);
    }
    return rows;
  }

  async function localizeMissing(items) {
    const ids = items
      .filter(item => item.needs_localization)
      .map(item => String(item.id || item.item_id || ''))
      .filter(id => id && !localizedCache.has(id) && !localizationInFlight.has(id))
      .slice(0, 8);
    if (!ids.length) return;
    ids.forEach(id => localizationInFlight.add(id));
    try {
      await localizeIds(ids);
      renderLatest();
    } catch (_) {
      // Live polling stays responsive; persistence allows a later retry.
    } finally {
      ids.forEach(id => localizationInFlight.delete(id));
    }
  }

  function telegramPreviewText(value) {
    return String(value || '')
      .replace(/<a\b[^>]*>(.*?)<\/a>/gi, '$1')
      .replace(/<\/?(?:b|strong|i|em|u|s|code|pre)>/gi, '')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  }

  function finalOutputBlock(item) {
    const box = document.createElement('section');
    box.className = 'final-output-box live-final-output';
    const label = document.createElement('strong');
    label.textContent = 'خروجی نهایی تلگرام';
    const pre = document.createElement('pre');
    pre.textContent = item.final_message ? telegramPreviewText(item.final_message) : 'در حال آماده‌سازی نسخه نهایی فارسی…';
    box.append(label, pre);
    return box;
  }

  function sourceDetails(item) {
    if (!item.original_title && !item.original_body) return null;
    const details = document.createElement('details');
    details.className = 'original-source-text';
    const summary = document.createElement('summary');
    summary.textContent = 'متن اصلی منبع';
    const pre = document.createElement('pre');
    pre.textContent = [item.original_title, item.original_body].filter(Boolean).join('\n\n');
    details.append(summary, pre);
    return details;
  }

  async function ensureLocalized(item) {
    const id = String(item.id || item.item_id || '');
    const merged = mergeLocalized(item);
    if (!merged.needs_localization && merged.final_message) return merged;
    const rows = await localizeIds([id]);
    const localized = rows.find(row => String(row.id || row.item_id || '') === id);
    return localized || mergeLocalized(item);
  }

  function actionButton(label, className = 'button') {
    const button = document.createElement('button');
    button.className = className;
    button.type = 'button';
    button.textContent = label;
    return button;
  }

  function renderFeed(items) {
    const frag = document.createDocumentFragment();
    for (const item of items) {
      const id = String(item.id || item.item_id || '');
      const row = document.createElement('article');
      row.className = `live-news-row status-${item.panel_status || 'new'}`;
      row.dataset.newsId = id;

      const check = document.createElement('input');
      check.type = 'checkbox'; check.className = 'live-select'; check.value = id; check.setAttribute('aria-label', 'انتخاب خبر');
      check.addEventListener('change', syncBulkState); row.appendChild(check);
      const rail = document.createElement('div'); rail.className = 'news-status-rail'; row.appendChild(rail);

      const content = document.createElement('div'); content.className = 'live-news-copy';
      const titleLine = document.createElement('div'); titleLine.className = 'news-title-line';
      const title = document.createElement('strong'); title.textContent = item.title || 'عنوان فارسی در حال آماده‌سازی';
      titleLine.appendChild(title); content.appendChild(titleLine);
      const meta = document.createElement('small');
      meta.textContent = [item.source, item.panel_status_fa, item.decision_reason_fa, item.published_at_source ? `زمان منبع: ${faTime(item.published_at_source)}` : ''].filter(Boolean).join(' · ');
      content.appendChild(meta);
      if (item.body) {
        const body = document.createElement('p'); body.className = 'persian-body'; body.textContent = item.body; content.appendChild(body);
      }
      content.appendChild(finalOutputBlock(item));
      const original = sourceDetails(item); if (original) content.appendChild(original);
      row.appendChild(content);

      const actions = document.createElement('div'); actions.className = 'live-news-actions newsroom-live-actions';
      if (item.can_publish && id) {
        const publish = actionButton('انتشار', 'button publish-button');
        publish.addEventListener('click', async () => {
          publish.disabled = true; const old = publish.textContent; publish.textContent = 'آماده‌سازی…';
          try {
            const finalItem = await ensureLocalized(item);
            if (!finalItem.final_message) throw new Error('نسخه نهایی فارسی هنوز آماده نیست');
            const data = await postJson(`/api/command-center/live/${encodeURIComponent(id)}/publish`);
            publish.textContent = 'در حال انتشار…';
            const result = await watchCommand(data.command_id, 'انتشار خبر');
            if (result?.status === 'failed') throw new Error(result.message || 'انتشار ناموفق بود');
          } catch (error) {
            if (commandResult) commandResult.textContent = `انتشار خبر: ${error.message}`;
          } finally { publish.disabled = false; publish.textContent = old; }
        });
        actions.appendChild(publish);
      }

      if (item.can_reject && id) {
        const reject = actionButton('رد', 'button reject-button');
        reject.addEventListener('click', async () => {
          reject.disabled = true; const old = reject.textContent; reject.textContent = 'در حال رد…';
          try {
            await postJson(`/api/command-center/live/${encodeURIComponent(id)}/reject`);
            if (commandResult) commandResult.textContent = 'خبر رد شد.';
            row.remove();
            await refreshLiveFeed();
          } catch (error) {
            if (commandResult) commandResult.textContent = `رد خبر: ${error.message}`;
            reject.disabled = false; reject.textContent = old;
          }
        });
        actions.appendChild(reject);
      }

      if (item.review_url) {
        const edit = document.createElement('a'); edit.className = 'button'; edit.href = item.review_url; edit.textContent = 'ویرایش'; actions.appendChild(edit);
      } else if (item.can_review && id) {
        const edit = actionButton('ویرایش');
        edit.addEventListener('click', async () => {
          edit.disabled = true; const old = edit.textContent; edit.textContent = 'در حال آماده‌سازی…';
          try {
            if (item.needs_localization) await ensureLocalized(item);
            const data = await postJson(`/api/command-center/live/${encodeURIComponent(id)}/review`);
            if (data.review_url) window.location.assign(data.review_url);
          } catch (error) {
            if (commandResult) commandResult.textContent = `ویرایش خبر: ${error.message}`;
            edit.disabled = false; edit.textContent = old;
          }
        });
        actions.appendChild(edit);
      }

      if (item.source_url) {
        const source = document.createElement('a'); source.className = 'button source-button'; source.href = item.source_url; source.target = '_blank'; source.rel = 'noopener'; source.textContent = 'منبع'; actions.appendChild(source);
      }

      const del = actionButton('حذف', 'button danger-lite');
      del.addEventListener('click', async () => {
        del.disabled = true; del.textContent = 'در حال حذف…';
        try {
          const data = await postJson('/api/command-center/clear', { scope: 'live', ids: [id] });
          if (commandResult) commandResult.textContent = data.message || 'خبر حذف شد.';
          row.remove();
          await refreshLiveFeed();
        } catch (error) {
          if (commandResult) commandResult.textContent = `حذف خبر: ${error.message}`;
          del.disabled = false; del.textContent = 'حذف';
        }
      });
      actions.appendChild(del); row.appendChild(actions); frag.appendChild(row);
    }
    if (!items.length) {
      const empty = document.createElement('div'); empty.className = 'empty-state'; empty.textContent = 'هنوز خبر تازه‌ای وارد نشده.'; frag.appendChild(empty);
    }
    feed.replaceChildren(frag);
    syncBulkState();
  }

  async function refreshLiveFeed() {
    try {
      const data = await getJson('/api/live-feed');
      const items = Array.isArray(data.items) ? data.items : [];
      const nextFirst = String(items[0]?.id || '');
      if (nextFirst && firstId && nextFirst !== firstId) { beep(); showBadge(); document.title = '🔴 خبر جدید | بی‌خبر'; }
      if (nextFirst) firstId = nextFirst;
      latestItems = items;
      renderLatest();
      void localizeMissing(items);
      if (liveCount) liveCount.textContent = String(data.count ?? items.length);
    } catch (_) {}
  }

  async function refreshStatus() {
    try {
      const data = await getJson('/api/command-center/status');
      publishingEnabled = Boolean(data.publishing); paintPublishing();
      if (queueCount) queueCount.textContent = String(data.queue_count ?? '0');
      document.querySelectorAll('[data-module-card]').forEach(card => {
        const name = card.dataset.moduleCard;
        const status = card.querySelector('.module-status');
        const available = Boolean(data.modules?.[name]?.available);
        if (status) status.textContent = available ? 'آماده' : 'در دسترس نیست';
      });
    } catch (_) {}
  }

  async function refreshHealth() {
    try {
      const data = await getJson('/api/command-center/health');
      const agentFa = { active: 'فعال', stale: 'بدون heartbeat تازه', unknown: 'نامشخص' }[data.agent_state] || 'نامشخص';
      const tgFa = { ok: 'سالم', error: 'خطا', unknown: 'نامشخص' }[data.telegram_state] || 'نامشخص';
      setText('agentState', agentFa); setText('lastCycleAt', faTime(data.last_cycle_at)); setText('telegramState', tgFa);
      setText('healthCycle', faTime(data.last_cycle_at)); setText('healthCycleState', agentFa);
      setText('healthPublication', faTime(data.last_publication_at)); setText('healthTelegram', tgFa); setText('healthError', data.last_error || '—');
    } catch (_) {
      setText('agentState', 'نامشخص'); setText('telegramState', 'نامشخص');
    }
  }

  function renderPreview(body, data) {
    body.replaceChildren();
    if (data.image_url) {
      const image = document.createElement('img');
      image.className = 'module-preview-image';
      image.alt = 'پیش‌نمایش ترافیک هوایی';
      image.loading = 'eager';
      image.src = `${data.image_url}?t=${encodeURIComponent(data.generated_at || Date.now())}`;
      body.appendChild(image);
    }
    const pre = document.createElement('pre'); pre.textContent = telegramPreviewText(data.message || ''); body.appendChild(pre);
    if (data.available_for_publish === false) {
      const note = document.createElement('small'); note.className = 'preview-warning'; note.textContent = 'این پیش‌نمایش قابل مشاهده است، اما به‌دلیل نبود عدد دقیق قابل استناد، انتشار خودکار آن غیرفعال است.'; body.appendChild(note);
    }
    if (data.generated_at) {
      const small = document.createElement('small');
      small.textContent = `ساخته‌شده: ${faTime(data.generated_at)}`;
      body.appendChild(small);
    }
  }

  async function loadPreview(name, panel) {
    const body = panel.querySelector('.module-preview-body');
    if (!body) return;
    body.textContent = 'در حال دریافت پیش‌نمایش…';
    try {
      let data = await getJson(`/api/command-center/module/${name}/preview`);
      if (!data.available || !data.message) {
        body.textContent = 'در حال ساخت پیش‌نمایش واقعی…';
        const queued = await postJson(`/api/command-center/module/${name}/preview`);
        const result = await watchCommand(queued.command_id, 'ساخت پیش‌نمایش');
        if (!result || result.status === 'failed') {
          body.textContent = result?.message ? `ساخت پیش‌نمایش ناموفق بود: ${result.message}` : 'نتیجه ساخت پیش‌نمایش از ایجنت نرسید.';
          return;
        }
        data = await getJson(`/api/command-center/module/${name}/preview`);
      }
      if (!data.available || !data.message) {
        body.textContent = 'داده واقعی کافی برای پیش‌نمایش موجود نیست.';
        return;
      }
      renderPreview(body, data);
    } catch (error) { body.textContent = `خطا در دریافت پیش‌نمایش: ${error.message}`; }
  }

  document.querySelectorAll('[data-preview-toggle]').forEach(button => {
    button.addEventListener('click', async event => {
      event.stopPropagation();
      const name = button.dataset.previewToggle;
      const panel = document.querySelector(`[data-preview-panel="${name}"]`);
      if (!panel) return;
      const opening = panel.hidden;
      panel.hidden = !opening;
      if (opening) await loadPreview(name, panel);
    });
  });

  document.querySelectorAll('[data-command-module]').forEach(button => {
    button.addEventListener('click', async () => {
      const name = button.dataset.commandModule;
      const old = button.textContent; button.disabled = true; button.textContent = 'در حال ارسال…';
      try {
        const data = await postJson(`/api/command-center/module/${name}`);
        if (commandResult) commandResult.textContent = `${old}: در صف اجرا`;
        void watchCommand(data.command_id, old);
      } catch (error) { if (commandResult) commandResult.textContent = `${old}: ${error.message}`; }
      finally { button.disabled = false; button.textContent = old; }
    });
  });

  liveSelectAll?.addEventListener('change', () => {
    feed.querySelectorAll('.live-select').forEach(box => { box.checked = liveSelectAll.checked; });
    syncBulkState();
  });

  liveBulkDelete?.addEventListener('click', async () => {
    const ids = selectedIds();
    if (!ids.length) return;
    liveBulkDelete.disabled = true;
    if (liveBulkState) liveBulkState.textContent = 'در حال حذف…';
    try {
      const data = await postJson('/api/command-center/clear', { scope: 'live', ids });
      if (liveBulkState) liveBulkState.textContent = data.message || 'حذف شد.';
      await refreshLiveFeed();
    } catch (error) {
      if (liveBulkState) liveBulkState.textContent = `خطا: ${error.message}`;
    } finally { syncBulkState(); }
  });

  panicToggle?.addEventListener('click', async () => {
    panicToggle.disabled = true;
    try {
      const data = await postJson('/api/command-center/publishing', { enabled: !publishingEnabled });
      publishingEnabled = Boolean(data.publishing); paintPublishing();
      if (commandResult) commandResult.textContent = publishingEnabled ? 'انتشار فعال شد.' : 'انتشار متوقف شد.';
    } catch (error) { if (commandResult) commandResult.textContent = `خطا: ${error.message}`; }
    finally { panicToggle.disabled = false; }
  });

  soundToggle.addEventListener('click', async () => {
    soundOn = !soundOn; localStorage.setItem('bikhabar_sound_alert', soundOn ? 'on' : 'off'); paintSound();
    if (soundOn) { try { audioContext ||= new (window.AudioContext || window.webkitAudioContext)(); await audioContext.resume?.(); beep(); } catch (_) {} }
  });

  document.addEventListener('visibilitychange', () => { if (!document.hidden) document.title = 'اتاق خبر | بی‌خبر'; });
  paintSound(); paintPublishing();
  refreshLiveFeed(); refreshStatus(); refreshHealth();
  window.setInterval(refreshLiveFeed, 1000);
  window.setInterval(() => { refreshStatus(); refreshHealth(); }, 2000);
})();
