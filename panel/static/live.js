(() => {
  const feed = document.getElementById('liveFeed');
  const toggle = document.getElementById('soundToggle');
  const badge = document.getElementById('newNewsBadge');
  const connection = document.getElementById('liveConnection');
  const healthLiveState = document.getElementById('healthLiveState');
  const updatedAt = document.getElementById('liveUpdatedAt');
  const liveCount = document.getElementById('liveCount');
  const queueCount = document.getElementById('queueCount');
  const publishingState = document.getElementById('publishingState');
  const panicToggle = document.getElementById('panicToggle');
  const commandResult = document.getElementById('commandResult');
  const pollSeconds = document.getElementById('pollSeconds');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (!feed || !toggle) return;

  const FEED_INTERVAL_MS = 1000;
  const HIDDEN_INTERVAL_MS = 5000;
  const STATUS_INTERVAL_MS = 5000;
  let soundOn = localStorage.getItem('bikhabar_sound_alert') !== 'off';
  let firstId = feed.querySelector('[data-news-id]')?.dataset.newsId || '';
  let audioContext = null;
  let publishingEnabled = true;
  let feedInFlight = false;
  let liveTimer = null;

  const bulkBar = document.createElement('div');
  bulkBar.className = 'live-bulk-toolbar';
  bulkBar.innerHTML = '<label><input id="liveSelectAll" type="checkbox"> انتخاب همه</label><button id="liveBulkDelete" class="button" type="button" disabled>پاک کردن انتخاب‌شده‌ها</button><small id="liveBulkState"></small>';
  feed.parentElement?.insertBefore(bulkBar, feed);
  const selectAll = document.getElementById('liveSelectAll');
  const bulkDelete = document.getElementById('liveBulkDelete');
  const bulkState = document.getElementById('liveBulkState');

  function paintToggle() {
    toggle.setAttribute('aria-pressed', soundOn ? 'true' : 'false');
    toggle.textContent = soundOn ? '🔔 صدا روشن' : '🔕 صدا خاموش';
    toggle.classList.toggle('muted-toggle', !soundOn);
  }

  function paintPublishing() {
    if (!publishingState || !panicToggle) return;
    publishingState.textContent = publishingEnabled ? 'فعال' : 'متوقف';
    publishingState.classList.toggle('ok', publishingEnabled);
    publishingState.classList.toggle('offline', !publishingEnabled);
    panicToggle.textContent = publishingEnabled ? '⛔ توقف کامل انتشار' : '▶️ ازسرگیری انتشار';
    panicToggle.classList.toggle('resume-button', !publishingEnabled);
  }

  function beep() {
    if (!soundOn) return;
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(920, audioContext.currentTime);
      gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.14, audioContext.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.2);
      oscillator.connect(gain); gain.connect(audioContext.destination);
      oscillator.start(); oscillator.stop(audioContext.currentTime + 0.22);
    } catch (_) {}
  }

  function showBadge() {
    if (!badge) return;
    badge.hidden = false;
    badge.classList.remove('pop'); void badge.offsetWidth; badge.classList.add('pop');
    window.clearTimeout(showBadge.timer);
    showBadge.timer = window.setTimeout(() => { badge.hidden = true; }, 5000);
  }

  function paintConnection(isOnline) {
    const text = isOnline ? 'متصل' : 'در حال اتصال مجدد…';
    if (connection) {
      connection.textContent = text;
      connection.classList.toggle('ok', isOnline);
      connection.classList.toggle('offline', !isOnline);
    }
    if (healthLiveState) {
      healthLiveState.textContent = isOnline ? 'ONLINE' : 'RECONNECTING';
      healthLiveState.classList.toggle('ok', isOnline);
      healthLiveState.classList.toggle('offline', !isOnline);
    }
  }

  function selectedIds() {
    return Array.from(feed.querySelectorAll('.live-select:checked')).map(box => box.value).filter(Boolean);
  }

  function syncBulk() {
    const boxes = Array.from(feed.querySelectorAll('.live-select'));
    const selected = boxes.filter(box => box.checked).length;
    if (bulkDelete) bulkDelete.disabled = selected === 0;
    if (selectAll) {
      selectAll.checked = boxes.length > 0 && selected === boxes.length;
      selectAll.indeterminate = selected > 0 && selected < boxes.length;
    }
    if (bulkState) bulkState.textContent = selected ? `${selected.toLocaleString('fa-IR')} خبر انتخاب شده` : '';
  }

  function ageText(seconds) {
    const value = Math.max(0, Number(seconds || 0));
    if (value < 60) return `${Math.floor(value).toLocaleString('fa-IR')} ثانیه پیش`;
    if (value < 3600) return `${Math.floor(value / 60).toLocaleString('fa-IR')} دقیقه پیش`;
    return `${Math.floor(value / 3600).toLocaleString('fa-IR')} ساعت پیش`;
  }

  function makeText(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text || '';
    return el;
  }

  function ensureRow(item, selected) {
    const id = String(item.id || item.item_id || '');
    let row = feed.querySelector(`[data-news-id="${CSS.escape(id)}"]`);
    if (!row) {
      row = document.createElement('article');
      row.dataset.newsId = id;
      row.innerHTML = '<input type="checkbox" class="live-select" aria-label="انتخاب خبر"><div class="news-status-rail"></div><div class="live-news-copy"><div class="news-title-line"><strong class="live-title"></strong></div><div class="news-time-line"></div><small class="live-meta"></small><details class="original-news" hidden><summary>نمایش متن اصلی</summary><div class="original-news-text" dir="ltr"></div></details></div><div class="live-news-actions"></div>';
      row.querySelector('.live-select').addEventListener('change', syncBulk);
    }
    row.className = `live-news-row status-${item.panel_status || 'new'}`;
    const checkbox = row.querySelector('.live-select');
    checkbox.value = id; checkbox.checked = selected.has(id);
    row.querySelector('.live-title').textContent = item.title_fa || item.title || 'عنوان فارسی در حال آماده‌سازی';

    const timeLine = row.querySelector('.news-time-line');
    timeLine.replaceChildren();
    if (item.source_time_fa) timeLine.appendChild(makeText('span', 'time-chip source-time', `زمان منبع: ${item.source_time_fa}`));
    if (item.arrival_time_fa) timeLine.appendChild(makeText('span', 'time-chip arrival-time', `ورود به پنل: ${item.arrival_time_fa}`));
    const age = makeText('span', 'time-chip age-time', ageText(item.age_seconds));
    age.dataset.ageSeconds = String(item.age_seconds || 0); timeLine.appendChild(age);

    row.querySelector('.live-meta').textContent = [item.source, item.panel_status_fa, item.decision_reason_fa].filter(Boolean).join(' · ');
    const details = row.querySelector('.original-news');
    if (item.has_original && item.original_title) {
      details.hidden = false;
      details.querySelector('.original-news-text').textContent = item.original_title;
    } else {
      details.hidden = true; details.open = false;
    }

    const actions = row.querySelector('.live-news-actions');
    actions.replaceChildren();
    if (item.source_url) {
      const link = makeText('a', 'button source-button', 'منبع');
      link.href = item.source_url; link.target = '_blank'; link.rel = 'noopener'; actions.appendChild(link);
    }
    return row;
  }

  function renderFeed(items) {
    const selected = new Set(selectedIds());
    const wanted = new Set(items.map(item => String(item.id || item.item_id || '')));
    feed.querySelectorAll('[data-news-id]').forEach(row => {
      if (!wanted.has(row.dataset.newsId || '')) row.remove();
    });
    if (!items.length) {
      if (!feed.querySelector('.empty-state')) feed.replaceChildren(makeText('div', 'empty-state', 'هنوز خبر تازه‌ای در فید ثبت نشده.'));
      syncBulk(); return;
    }
    feed.querySelector('.empty-state')?.remove();
    const fragment = document.createDocumentFragment();
    for (const item of items) fragment.appendChild(ensureRow(item, selected));
    feed.appendChild(fragment);
    syncBulk();
  }

  function tickAges() {
    feed.querySelectorAll('[data-age-seconds]').forEach(el => {
      const next = Number(el.dataset.ageSeconds || 0) + 1;
      el.dataset.ageSeconds = String(next); el.textContent = ageText(next);
    });
  }

  function applyCapabilities(modules = {}) {
    document.querySelectorAll('[data-command-module]').forEach(button => {
      const name = button.dataset.commandModule;
      const capability = modules[name];
      if (!capability) return;
      const card = document.querySelector(`[data-module-card="${name}"]`);
      const status = card?.querySelector('.module-status');
      if (capability.available) {
        button.disabled = false; button.dataset.unavailable = '0';
        if (status) { status.textContent = 'آماده'; status.classList.add('ok'); status.classList.remove('warn'); }
      } else {
        button.disabled = true; button.dataset.unavailable = '1';
        if (status) { status.textContent = 'در حال اتصال'; status.classList.remove('ok'); status.classList.add('warn'); }
      }
    });
  }

  async function refreshStatus() {
    try {
      const response = await fetch('/api/command-center/status', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      publishingEnabled = Boolean(data.publishing); paintPublishing(); applyCapabilities(data.modules || {});
      if (queueCount) queueCount.textContent = String(data.queue_count ?? queueCount.textContent);
      if (pollSeconds) pollSeconds.textContent = `${Number(data.poll_seconds || 5).toLocaleString('fa-IR')} ثانیه`;
    } catch (_) {}
  }

  function scheduleLive() {
    window.clearTimeout(liveTimer);
    liveTimer = window.setTimeout(refreshLiveFeed, document.hidden ? HIDDEN_INTERVAL_MS : FEED_INTERVAL_MS);
  }

  async function refreshLiveFeed() {
    if (feedInFlight) { scheduleLive(); return; }
    feedInFlight = true;
    try {
      const response = await fetch('/api/live-feed', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const items = Array.isArray(data.items) ? data.items : [];
      const nextFirst = items[0]?.id || '';
      if (nextFirst && firstId && nextFirst !== firstId) { beep(); showBadge(); document.title = '🔴 خبر جدید | بی‌خبر'; }
      if (nextFirst) firstId = nextFirst;
      renderFeed(items);
      if (liveCount) liveCount.textContent = String(data.count ?? items.length);
      paintConnection(true);
      if (updatedAt) updatedAt.textContent = `آخرین همگام‌سازی ${new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · هر ۱ ثانیه`;
    } catch (_) { paintConnection(false); }
    finally { feedInFlight = false; scheduleLive(); }
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

  selectAll?.addEventListener('change', () => {
    feed.querySelectorAll('.live-select').forEach(box => { box.checked = selectAll.checked; }); syncBulk();
  });
  bulkDelete?.addEventListener('click', async () => {
    const ids = selectedIds(); if (!ids.length) return;
    bulkDelete.disabled = true;
    try {
      await postJson('/api/command-center/clear', { scope: 'live', ids });
      const targets = new Set(ids);
      feed.querySelectorAll('[data-news-id]').forEach(row => { if (targets.has(row.dataset.newsId)) row.remove(); });
      if (bulkState) bulkState.textContent = 'پاک‌سازی ثبت شد';
      window.setTimeout(refreshLiveFeed, 500);
    } catch (error) { if (bulkState) bulkState.textContent = `خطا: ${error.message}`; }
    finally { syncBulk(); }
  });

  toggle.addEventListener('click', async () => {
    soundOn = !soundOn; localStorage.setItem('bikhabar_sound_alert', soundOn ? 'on' : 'off');
    if (soundOn) { try { audioContext ||= new (window.AudioContext || window.webkitAudioContext)(); if (audioContext.state === 'suspended') await audioContext.resume(); beep(); } catch (_) {} }
    paintToggle();
  });

  panicToggle?.addEventListener('click', async () => {
    panicToggle.disabled = true;
    try {
      const data = await postJson('/api/command-center/publishing', { enabled: !publishingEnabled });
      publishingEnabled = Boolean(data.publishing); paintPublishing();
      if (commandResult) commandResult.textContent = publishingEnabled ? 'انتشار دوباره فعال شد.' : 'انتشار فوراً متوقف شد.';
    } catch (error) { if (commandResult) commandResult.textContent = `خطا: ${error.message}`; }
    finally { panicToggle.disabled = false; }
  });

  document.querySelectorAll('[data-command-module]').forEach(button => {
    button.addEventListener('click', async () => {
      if (button.dataset.unavailable === '1') return;
      const moduleName = button.dataset.commandModule; button.disabled = true; const old = button.textContent; button.textContent = 'در صف…';
      try {
        await postJson(`/api/command-center/module/${moduleName}`);
        if (commandResult) commandResult.textContent = 'فرمان ثبت شد؛ ایجنت VPS طی چند ثانیه آن را اجرا می‌کند.';
      } catch (error) { if (commandResult) commandResult.textContent = `خطا: ${error.message}`; }
      finally { window.setTimeout(() => { if (button.dataset.unavailable !== '1') button.disabled = false; button.textContent = old; }, 900); }
    });
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) document.title = 'اتاق فرمان جنگ | بی‌خبر';
    scheduleLive();
  });
  paintToggle(); paintPublishing(); paintConnection(true); refreshStatus(); refreshLiveFeed();
  window.setInterval(refreshStatus, STATUS_INTERVAL_MS);
  window.setInterval(tickAges, 1000);
})();
