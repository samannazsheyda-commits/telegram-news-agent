(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const toastStack = document.getElementById('nrToastStack');
  const confirmSheet = document.getElementById('confirmSheet');
  const confirmTitle = document.getElementById('confirmTitle');
  const confirmText = document.getElementById('confirmText');
  const confirmAccept = document.getElementById('confirmAccept');
  const soundToggle = document.getElementById('soundToggle');
  let confirmResolve = null;

  function toast(message, kind = '') {
    if (!toastStack || !message) return;
    const node = document.createElement('div');
    node.className = `nr-toast ${kind}`.trim();
    node.textContent = message;
    toastStack.appendChild(node);
    window.setTimeout(() => node.remove(), 3600);
  }

  function closeConfirm(value = false) {
    if (!confirmSheet) return;
    confirmSheet.hidden = true;
    document.body.style.overflow = '';
    const resolve = confirmResolve;
    confirmResolve = null;
    if (resolve) resolve(value);
  }

  function confirmAction({title = 'تأیید عملیات', text = 'از انجام این عملیات مطمئنی؟', accept = 'تأیید'} = {}) {
    if (!confirmSheet || !confirmAccept) return Promise.resolve(window.confirm(text));
    if (confirmResolve) closeConfirm(false);
    confirmTitle.textContent = title;
    confirmText.textContent = text;
    confirmAccept.textContent = accept;
    confirmSheet.hidden = false;
    document.body.style.overflow = 'hidden';
    return new Promise(resolve => { confirmResolve = resolve; });
  }

  confirmAccept?.addEventListener('click', () => closeConfirm(true));
  confirmSheet?.querySelectorAll('[data-sheet-close]').forEach(node => node.addEventListener('click', () => closeConfirm(false)));
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape' && confirmSheet && !confirmSheet.hidden) closeConfirm(false);
  });

  function relativeTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return 'همین حالا';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes.toLocaleString('fa-IR')} دقیقه پیش`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours.toLocaleString('fa-IR')} ساعت پیش`;
    return date.toLocaleDateString('fa-IR', {month:'short', day:'numeric'});
  }

  function csrfHeaders(extra = {}) {
    return {'X-CSRFToken': csrf, ...extra};
  }

  let soundEnabled = localStorage.getItem('bikhabar-news-sound') === '1';
  function syncSoundButton() {
    if (!soundToggle) return;
    soundToggle.textContent = soundEnabled ? '🔔' : '🔕';
    soundToggle.setAttribute('aria-pressed', soundEnabled ? 'true' : 'false');
  }
  function ping() {
    if (!soundEnabled) return;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 660;
      gain.gain.setValueAtTime(0.035, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.13);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(); osc.stop(ctx.currentTime + 0.14);
      osc.addEventListener('ended', () => ctx.close().catch(() => {}));
    } catch (_) {}
  }
  soundToggle?.addEventListener('click', () => {
    soundEnabled = !soundEnabled;
    localStorage.setItem('bikhabar-news-sound', soundEnabled ? '1' : '0');
    syncSoundButton();
    if (soundEnabled) ping();
  });
  syncSoundButton();

  window.BikhabarUI = {toast, confirmAction, relativeTime, csrfHeaders, ping};
})();
