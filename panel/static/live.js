(() => {
  const feed = document.getElementById('liveFeed');
  const toggle = document.getElementById('soundToggle');
  const badge = document.getElementById('newNewsBadge');
  const connection = document.getElementById('liveConnection');
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
      oscillator.frequency.setValueAtTime(880, audioContext.currentTime);
      gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.16, audioContext.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.18);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.2);
    } catch (_) {}
  }

  function showBadge() {
    if (!badge) return;
    badge.hidden = false;
    badge.classList.remove('pop');
    void badge.offsetWidth;
    badge.classList.add('pop');
    window.clearTimeout(showBadge.timer);
    showBadge.timer = window.setTimeout(() => { badge.hidden = true; }, 5000);
  }

  async function refreshStatus() {
    try {
      const response = await fetch('/api/command-center/status', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      publishingEnabled = Boolean(data.publishing);
      paintPublishing();
      if (queueCount) queueCount.textContent = String(data.queue_count ?? queueCount.textContent);
      if (pollSeconds) pollSeconds.textContent = `${Number(data.poll_seconds || 5).toLocaleString('fa-IR')} ثانیه`;
    } catch (_) {}
  }

  async function refreshLiveFeed() {
    try {
      const response = await fetch(window.location.pathname, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'X-Bikhabar-Live': '1' },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const html = await response.text();
      const parsed = new DOMParser().parseFromString(html, 'text/html');
      const nextFeed = parsed.getElementById('liveFeed');
      if (!nextFeed) throw new Error('live-feed-missing');

      const nextFirst = nextFeed.querySelector('[data-news-id]')?.dataset.newsId || '';
      if (nextFirst && firstId && nextFirst !== firstId) {
        beep();
        showBadge();
        document.title = '🔴 خبر جدید | بی‌خبر';
      }
      if (nextFirst) firstId = nextFirst;

      feed.replaceChildren(...Array.from(nextFeed.childNodes).map(node => document.importNode(node, true)));
      if (liveCount) liveCount.textContent = String(feed.querySelectorAll('[data-news-id]').length);
      if (connection) {
        connection.textContent = 'متصل';
        connection.classList.add('ok');
        connection.classList.remove('offline');
      }
      if (updatedAt) {
        updatedAt.textContent = `آخرین همگام‌سازی ${new Date().toLocaleTimeString('fa-IR', {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
      }
    } catch (_) {
      if (connection) {
        connection.textContent = 'در حال اتصال مجدد…';
        connection.classList.remove('ok');
        connection.classList.add('offline');
      }
    }
  }

  async function postJson(url, payload = {}) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  toggle.addEventListener('click', async () => {
    soundOn = !soundOn;
    localStorage.setItem('bikhabar_sound_alert', soundOn ? 'on' : 'off');
    if (soundOn) {
      try {
        audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
        if (audioContext.state === 'suspended') await audioContext.resume();
        beep();
      } catch (_) {}
    }
    paintToggle();
  });

  panicToggle?.addEventListener('click', async () => {
    panicToggle.disabled = true;
    try {
      const data = await postJson('/api/command-center/publishing', { enabled: !publishingEnabled });
      publishingEnabled = Boolean(data.publishing);
      paintPublishing();
      if (commandResult) commandResult.textContent = publishingEnabled ? 'انتشار دوباره فعال شد.' : 'انتشار فوراً متوقف شد.';
    } catch (error) {
      if (commandResult) commandResult.textContent = `خطا: ${error.message}`;
    } finally {
      panicToggle.disabled = false;
    }
  });

  document.querySelectorAll('[data-command-module]').forEach((button) => {
    button.addEventListener('click', async () => {
      const moduleName = button.dataset.commandModule;
      button.disabled = true;
      const old = button.textContent;
      button.textContent = 'در صف…';
      try {
        await postJson(`/api/command-center/module/${moduleName}`);
        if (commandResult) commandResult.textContent = 'فرمان ثبت شد؛ ایجنت حداکثر تا چند ثانیه اجرا می‌کند.';
      } catch (error) {
        if (commandResult) commandResult.textContent = `خطا: ${error.message}`;
      } finally {
        window.setTimeout(() => { button.disabled = false; button.textContent = old; }, 1500);
      }
    });
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) document.title = 'اتاق فرمان | بی‌خبر';
  });

  paintToggle();
  paintPublishing();
  refreshStatus();
  window.setInterval(refreshLiveFeed, 3000);
  window.setInterval(refreshStatus, 5000);
})();