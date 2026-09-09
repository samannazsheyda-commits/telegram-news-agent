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

  let soundOn = localStorage.getItem('bikhabar_sound_alert') !== 'off';
  let firstId = feed.querySelector('[data-news-id]')?.dataset.newsId || '';
  let audioContext = null;
  let publishingEnabled = true;

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
    if (selectAll) selectAll.checked = boxes.length > 0 && selected === boxes.length;
    if (bulkState) bulkState.textContent = selected ? `${selected.toLocaleString('fa-IR')} انتخاب شده` : '';
  }

  function makeText(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text || '';
    return el;
  }

  function renderFeed(items) {
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const id = String(item.id || item.item_id || '');
      const row = document.createElement('article');
      row.className = `live-news-row status-${item.panel_status || 'new'}`;
      row.dataset.newsId = id;

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.className = 'live-select'; checkbox.value = id;
      checkbox.setAttribute('aria-label', 'انتخاب خبر');
      checkbox.addEventListener('change', syncBulk);
      row.appendChild(checkbox);

      const rail = document.createElement('div'); rail.className = 'news-status-rail'; row.appendChild(rail);
      const copy = document.createElement('div'); copy.className = 'live-news-copy';
      const line = makeText('div', 'news-title-line', '');
      line.appendChild(makeText('strong', '', item.title || 'بدون عنوان'));
      copy.appendChild(line);
      const meta = [item.source, item.panel_status_fa, item.decision_reason_fa].filter(Boolean).join(' · ');
      copy.appendChild(makeText('small', '', meta)); row.appendChild(copy);

      const actions = document.createElement('div'); actions.className = 'live-news-actions';
      if (item.source_url) {
        const link = makeText('a', 'button source-button', 'منبع');
        link.href = item.source_url; link.target = '_blank'; link.rel = 'noopener'; actions.appendChild(link);
      }
      row.appendChild(actions); fragment.appendChild(row);
    }
    if (!items.length) {
      const empty = makeText('div', 'empty-state', 'هنوز خبر تازه‌ای در فید ثبت نشده.');
      fragment.appendChild(empty);
    }
    feed.replaceChildren(fragment);
    syncBulk();
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
        button.disabled = true; button.dataset.unavailable = '1'; button.textContent = 'هنوز متصل نشده';
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

  async function refreshLiveFeed() {
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
      if (updatedAt) updatedAt.textContent = `آخرین همگام‌سازی ${new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
    } catch (_) { paintConnection(false); }
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
      if (bulkState) bulkState.textContent = 'برای پاک‌سازی ارسال شد';
      window.setTimeout(refreshLiveFeed, 1500);
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
      finally { window.setTimeout(() => { if (button.dataset.unavailable !== '1') button.disabled = false; button.textContent = old; }, 1200); }
    });
  });

  document.addEventListener('visibilitychange', () => { if (!document.hidden) document.title = 'اتاق فرمان جنگ | بی‌خبر'; });
  paintToggle(); paintPublishing(); paintConnection(true); refreshStatus(); refreshLiveFeed();
  window.setInterval(refreshLiveFeed, 3000); window.setInterval(refreshStatus, 5000);
})();
