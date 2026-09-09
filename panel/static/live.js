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
  const commandWatchers = new Map();

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
    if (!commandId || commandWatchers.has(commandId)) return;
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
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    commandWatchers.delete(commandId);
    if (commandResult) commandResult.textContent = `${label}: نتیجه هنوز از ایجنت نرسیده`;
  }

  function detailsBlock(item) {
    const details = document.createElement('details');
    details.className = 'news-details';
    const summary = document.createElement('summary');
    summary.textContent = 'جزئیات و خروجی نهایی';
    details.appendChild(summary);

    const body = document.createElement('div');
    body.className = 'news-details-body';
    if (item.body) {
      const p = document.createElement('p'); p.className = 'persian-body'; p.textContent = item.body; body.appendChild(p);
    }
    const final = document.createElement('section');
    final.className = 'final-output-box';
    const h = document.createElement('strong'); h.textContent = 'خروجی نهایی تلگرام'; final.appendChild(h);
    const pre = document.createElement('pre'); pre.textContent = item.final_message || 'خروجی نهایی هنوز آماده نشده.'; final.appendChild(pre);
    body.appendChild(final);

    if (item.original_title || item.original_body) {
      const original = document.createElement('details'); original.className = 'original-source-text';
      const originalSummary = document.createElement('summary'); originalSummary.textContent = 'متن اصلی منبع'; original.appendChild(originalSummary);
      const originalPre = document.createElement('pre'); originalPre.textContent = [item.original_title, item.original_body].filter(Boolean).join('\n\n'); original.appendChild(originalPre);
      body.appendChild(original);
    }
    details.appendChild(body);
    return details;
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
      const title = document.createElement('strong'); title.textContent = item.title || 'عنوان فارسی در حال آماده‌سازی';
      const titleLine = document.createElement('div'); titleLine.className = 'news-title-line'; titleLine.appendChild(title); content.appendChild(titleLine);
      const meta = document.createElement('small'); meta.textContent = [item.source, item.panel_status_fa, item.decision_reason_fa].filter(Boolean).join(' · '); content.appendChild(meta);
      content.appendChild(detailsBlock(item)); row.appendChild(content);

      const actions = document.createElement('div'); actions.className = 'live-news-actions';
      if (item.review_url) {
        const edit = document.createElement('a'); edit.className = 'button'; edit.href = item.review_url; edit.textContent = 'ویرایش / بررسی'; actions.appendChild(edit);
      }
      if (item.source_url) {
        const source = document.createElement('a'); source.className = 'button source-button'; source.href = item.source_url; source.target = '_blank'; source.rel = 'noopener'; source.textContent = 'منبع'; actions.appendChild(source);
      }
      const del = document.createElement('button'); del.className = 'button danger-lite'; del.type = 'button'; del.textContent = 'حذف';
      del.addEventListener('click', async () => {
        del.disabled = true; del.textContent = 'در حال حذف…';
        try {
          const data = await postJson('/api/command-center/clear', { scope: 'live', ids: [id] });
          await watchCommand(data.command_id, 'حذف خبر');
        } catch (error) { if (commandResult) commandResult.textContent = `حذف خبر: ${error.message}`; }
        finally { del.disabled = false; del.textContent = 'حذف'; }
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
      renderFeed(items);
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

  async function loadPreview(name, panel) {
    const body = panel.querySelector('.module-preview-body');
    if (body) body.textContent = 'در حال دریافت پیش‌نمایش…';
    try {
      const data = await getJson(`/api/command-center/module/${name}/preview`);
      if (!data.available || !data.message) {
        if (body) body.textContent = 'پیش‌نمایش موجود نیست. هنوز داده واقعی این ماژول ثبت نشده.';
        return;
      }
      if (body) {
        body.replaceChildren();
        const pre = document.createElement('pre'); pre.textContent = data.message; body.appendChild(pre);
        if (data.generated_at) { const small = document.createElement('small'); small.textContent = `ساخته‌شده: ${faTime(data.generated_at)}`; body.appendChild(small); }
      }
    } catch (error) { if (body) body.textContent = `خطا در دریافت پیش‌نمایش: ${error.message}`; }
  }

  document.querySelectorAll('[data-preview-toggle]').forEach(button => {
    button.addEventListener('click', async () => {
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
        watchCommand(data.command_id, old);
      } catch (error) { if (commandResult) commandResult.textContent = `${old}: ${error.message}`; }
      finally { button.disabled = false; button.textContent = old; }
    });
  });

  liveSelectAll?.addEventListener('change', () => {
    feed.querySelectorAll('.live-select').forEach(input => { input.checked = liveSelectAll.checked; });
    syncBulkState();
  });

  liveBulkDelete?.addEventListener('click', async () => {
    const ids = selectedIds();
    if (!ids.length) return;
    liveBulkDelete.disabled = true;
    if (liveBulkState) liveBulkState.textContent = 'در حال حذف…';
    try {
      const data = await postJson('/api/command-center/clear', { scope: 'live', ids });
      await watchCommand(data.command_id, 'حذف گروهی');
    } catch (error) {
      if (liveBulkState) liveBulkState.textContent = `خطا: ${error.message}`;
    } finally {
      syncBulkState();
    }
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
  paintSound(); paintPublishing(); syncBulkState();
  refreshLiveFeed(); refreshStatus(); refreshHealth();
  window.setInterval(refreshLiveFeed, 1000);
  window.setInterval(() => { refreshStatus(); refreshHealth(); }, 2000);
})();
