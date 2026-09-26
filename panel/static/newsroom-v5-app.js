(() => {
  'use strict';

  const storage = window.sessionStorage;
  const keys = {
    activeTab: 'v5.activeTab',
    reviewScroll: 'v5.reviewScroll',
    loadedCursor: 'v5.loadedCursor',
    selectedStory: 'v5.selectedStory',
    lunaDraft: 'v5.lunaDraft',
    lunaContextMarker: 'v5.lunaContextMarker',
  };
  const validTabs = new Set(['news', 'luna', 'published', 'control']);
  let eventSource = null;
  let eventFailures = 0;
  let pollingTimer = null;
  let reconnectTimer = null;
  let review = null;

  function toast(message, kind = 'info') {
    const node = document.getElementById('v5Toast');
    if (!node) return;
    node.textContent = message;
    node.dataset.kind = kind;
    node.hidden = false;
    window.clearTimeout(node._hideTimer);
    node._hideTimer = window.setTimeout(() => { node.hidden = true; }, 3200);
  }

  function confirmAction({ title, text, preview = '', danger = false }) {
    const dialog = document.getElementById('v5Confirm');
    if (!dialog?.showModal) return Promise.resolve(window.confirm(`${title}\n\n${preview}\n\n${text}`));
    document.getElementById('v5ConfirmTitle').textContent = title || 'تأیید';
    document.getElementById('v5ConfirmText').textContent = text || '';
    const previewNode = document.getElementById('v5ConfirmPreview');
    previewNode.textContent = preview;
    previewNode.hidden = !preview;
    document.getElementById('v5ConfirmAccept').classList.toggle('is-danger', Boolean(danger));
    return new Promise(resolve => {
      const close = () => {
        dialog.removeEventListener('close', close);
        resolve(dialog.returnValue === 'confirm');
      };
      dialog.addEventListener('close', close);
      dialog.showModal();
    });
  }

  window.NewsroomV5 = { confirm: confirmAction, toast };

  function currentTab() {
    const hash = window.location.hash.replace('#', '');
    if (validTabs.has(hash)) return hash;
    const saved = storage.getItem(keys.activeTab);
    return validTabs.has(saved) ? saved : 'news';
  }

  function selectTab(tab, { push = true } = {}) {
    if (!validTabs.has(tab)) tab = 'news';
    if (storage.getItem(keys.activeTab) === 'news') storage.setItem(keys.reviewScroll, String(window.scrollY || 0));
    storage.setItem(keys.activeTab, tab);
    document.getElementById('v5App')?.setAttribute('data-active-tab', tab);
    document.querySelectorAll('.v5-view').forEach(view => view.classList.toggle('is-active', view.dataset.view === tab));
    document.querySelectorAll('.v5-tab').forEach(button => button.classList.toggle('is-active', button.dataset.tab === tab));
    if (push && window.location.hash !== `#${tab}`) history.pushState({ tab }, '', `#${tab}`);
    if (tab === 'news') {
      requestAnimationFrame(() => window.scrollTo({ top: Number(storage.getItem(keys.reviewScroll) || 0), behavior: 'instant' }));
    } else if (tab === 'published') {
      loadPublished();
    } else if (tab === 'control') {
      loadHealth();
    }
  }

  async function loadHealth() {
    const mount = document.getElementById('v5Health');
    if (!mount) return;
    try {
      const response = await fetch('/api/v5/health', { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) return;
      const data = await response.json();
      const fmt = value => new Intl.NumberFormat('fa-IR').format(value || 0);
      const jobs = data.jobs || {};
      const failed = Object.values(jobs).reduce((sum, job) => sum + (job.failed || 0), 0);
      const values = {
        awaiting_translation: fmt(data.stories?.awaiting_translation),
        editorial_pending: fmt(jobs.editorial_story?.pending),
        outbox: fmt((data.publications?.pending || 0) + (data.publications?.retry || 0)),
        reconcile: fmt(data.publications?.reconcile),
        failed_jobs: fmt(failed),
        last_translation: data.last?.translation ? formatTime(data.last.translation) : '—',
      };
      for (const [key, value] of Object.entries(values)) {
        const node = mount.querySelector(`[data-health="${key}"]`);
        if (node) node.textContent = value;
      }
      const alert = document.getElementById('v5HealthAlert');
      if (alert) alert.hidden = !data.attention_required;
    } catch (_) {}
  }

  async function fetchCounts() {
    try {
      const response = await fetch('/api/v5/counts', { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) return;
      const data = await response.json();
      const reviewCount = document.getElementById('v5ReviewCount');
      const publishedCount = document.getElementById('v5PublishedCount');
      if (reviewCount) reviewCount.textContent = new Intl.NumberFormat('fa-IR').format(data.review || 0);
      if (publishedCount) publishedCount.textContent = new Intl.NumberFormat('fa-IR').format(data.published || 0);
    } catch (_) {}
  }

  async function loadPublished() {
    const mount = document.getElementById('v5PublishedList');
    if (!mount || mount.dataset.loading === '1') return;
    mount.dataset.loading = '1';
    try {
      const response = await fetch('/api/v5/published?limit=50', { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('published_fetch_failed');
      const data = await response.json();
      mount.innerHTML = (data.items || []).map(item => `
        <article class="v5-story-card is-published">
          <div class="v5-story-meta"><span>${escapeHtml(item.source_name || item.source_id || 'منبع')}</span><span>${escapeHtml(formatTime(item.published_at_source))}</span></div>
          <h2>${escapeHtml(item.title_fa || 'خبر منتشرشده')}</h2>
          ${item.body_fa ? `<p class="v5-story-body">${escapeHtml(item.body_fa)}</p>` : ''}
        </article>`).join('') || '<div class="v5-empty">هنوز انتشار V5 ثبت نشده.</div>';
    } catch (_) {
      mount.innerHTML = '<div class="v5-empty">آرشیو منتشرشده در دسترس نیست.</div>';
    } finally {
      mount.dataset.loading = '0';
    }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  }

  function formatTime(value) {
    if (!value) return '';
    try { return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)); }
    catch (_) { return String(value); }
  }

  function setConnection(state, text) {
    const node = document.getElementById('v5ConnectionStatus');
    if (!node) return;
    node.dataset.state = state;
    const label = node.querySelector('span:last-child');
    if (label) label.textContent = text;
  }

  function handleEvent(type, payload) {
    review?.onRealtime(type, payload);
    if (type === 'counts_changed' || type === 'story_added' || type === 'story_published' || type === 'story_rejected') fetchCounts();
    if (type === 'story_published' && currentTab() === 'published') loadPublished();
    if ((type === 'job_health_changed' || type === 'counts_changed') && currentTab() === 'control') loadHealth();
  }

  function connectEvents() {
    if (!window.EventSource || eventSource) {
      if (!window.EventSource) startPollingFallback();
      return;
    }
    setConnection('connecting', 'در حال اتصال');
    eventSource = new EventSource('/api/v5/events');
    eventSource.onopen = () => {
      eventFailures = 0;
      setConnection('live', 'زنده');
      stopPollingFallback();
      fetchCounts();
      review?.refreshTop();
    };
    const types = ['story_added', 'story_updated', 'story_published', 'story_rejected', 'counts_changed', 'job_health_changed', 'luna_status', 'refetch_required'];
    for (const type of types) {
      eventSource.addEventListener(type, event => {
        let payload = {};
        try { payload = JSON.parse(event.data || '{}'); } catch (_) {}
        handleEvent(type, payload);
      });
    }
    eventSource.onerror = () => {
      eventFailures += 1;
      setConnection('degraded', 'اتصال ناپایدار');
      if (eventFailures >= 3) {
        eventSource.close();
        eventSource = null;
        startPollingFallback();
        window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connectEvents, 60000);
      }
    };
  }

  function startPollingFallback() {
    if (pollingTimer) return;
    setConnection('polling', 'به‌روزرسانی دوره‌ای');
    const tick = () => {
      review?.refreshTop();
      fetchCounts();
    };
    tick();
    pollingTimer = window.setInterval(tick, 30000);
  }

  function stopPollingFallback() {
    if (!pollingTimer) return;
    window.clearInterval(pollingTimer);
    pollingTimer = null;
  }

  function handleLunaStory(event) {
    const story = event.detail?.story;
    if (!story?.id) return;
    storage.setItem(keys.selectedStory, story.id);
    storage.setItem(keys.lunaContextMarker, JSON.stringify({ id: story.id, title: story.title_fa || '' }));
    const mount = document.getElementById('v5LunaMount');
    if (mount) {
      mount.querySelector('strong').textContent = `زمینه Luna: ${story.title_fa}`;
      mount.querySelector('p').textContent = 'این خبر به‌عنوان زمینه ساختاریافته گفت‌وگو انتخاب شد.';
    }
    selectTab('luna');
  }

  function bindShell() {
    document.querySelectorAll('.v5-tab').forEach(button => button.addEventListener('click', () => selectTab(button.dataset.tab)));
    window.addEventListener('popstate', () => selectTab(currentTab(), { push: false }));
    window.addEventListener('v5:luna-story', handleLunaStory);
    window.addEventListener('beforeunload', () => {
      if (currentTab() === 'news') storage.setItem(keys.reviewScroll, String(window.scrollY || 0));
    });
    document.getElementById('v5OpenLegacyLuna')?.addEventListener('click', () => window.open('/luna', '_blank', 'noopener'));
    selectTab(currentTab(), { push: false });
  }

  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.register('/sw.js', { scope: '/v5' }).catch(() => {});
    navigator.serviceWorker.addEventListener('message', event => {
      if (event.data?.type !== 'NEW_VERSION_AVAILABLE') return;
      const banner = document.getElementById('v5VersionBanner');
      if (banner) banner.hidden = false;
    });
    document.getElementById('v5ReloadVersion')?.addEventListener('click', () => {
      window.location.replace(`${window.location.pathname}${window.location.search}${window.location.hash}`);
    });
  }

  function boot() {
    bindShell();
    review = new window.NewsroomV5Review.ReviewController({ onToast: toast, onCountsChanged: fetchCounts });
    review.start();
    fetchCounts();
    connectEvents();
    registerServiceWorker();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
