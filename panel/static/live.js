(() => {
  const feed = document.getElementById('liveFeed');
  const toggle = document.getElementById('soundToggle');
  const badge = document.getElementById('newNewsBadge');
  const connection = document.getElementById('liveConnection');
  const updatedAt = document.getElementById('liveUpdatedAt');
  const liveCount = document.getElementById('liveCount');
  if (!feed || !toggle) return;

  let soundOn = localStorage.getItem('bikhabar_sound_alert') !== 'off';
  let firstId = feed.querySelector('[data-news-id]')?.dataset.newsId || '';
  let audioContext = null;

  function paintToggle() {
    toggle.setAttribute('aria-pressed', soundOn ? 'true' : 'false');
    toggle.textContent = soundOn ? '🔔 صدا روشن' : '🔕 صدا خاموش';
    toggle.classList.toggle('muted-toggle', !soundOn);
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
    badge.hidden = false;
    badge.classList.remove('pop');
    void badge.offsetWidth;
    badge.classList.add('pop');
    window.clearTimeout(showBadge.timer);
    showBadge.timer = window.setTimeout(() => { badge.hidden = true; }, 5000);
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

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) document.title = 'داشبورد | بی‌خبر';
  });

  paintToggle();
  window.setInterval(refreshLiveFeed, 3000);
})();
