(() => {
  const feed = document.getElementById('liveFeed');
  if (!feed) return;

  const UI = window.BikhabarUI || {};
  const loadMore = document.getElementById('loadMoreFeed');
  const refreshButton = document.getElementById('refreshFeed');
  const fields = {
    engine: document.getElementById('engineState'),
    cycle: document.getElementById('lastCycleAt'),
    live: document.getElementById('liveCount'),
    published: document.getElementById('publishedCount'),
    dailyLimit: document.getElementById('dailyLimitLabel'),
    dailyRemaining: document.getElementById('dailyRemainingLabel'),
    dailyInput: document.getElementById('dailyLimitInput'),
    ready: document.getElementById('readyCount'),
    waiting: document.getElementById('waitingCount'),
    specialPublished: document.getElementById('specialPublished'),
    specialLimit: document.getElementById('specialLimitLabel'),
    sourcesOk: document.getElementById('sourcesOk'),
    sourcesFailed: document.getElementById('sourcesFailed'),
    fetched: document.getElementById('itemsFetched'),
    reason: document.getElementById('cycleReason'),
    error: document.getElementById('lastError'),
  };

  const machineCache = new Map();
  const machineInFlight = new Set();
  const machineFailures = new Set();
  const lunaCache = new Map();
  let stories = [];
  let visibleCount = 10;
  let timer = 0;
  let controller = null;
  let firstPaint = true;

  const esc = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const storyId = story => String(story?.id || story?.item_id || '').trim();

  function safeUrl(value) {
    try {
      const url = new URL(String(value || ''), window.location.origin);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch (_) {
      return '';
    }
  }

  function relativeTime(value) {
    return UI.relativeTime ? UI.relativeTime(value) : String(value || '');
  }

  function machineFor(story) {
    const id = storyId(story);
    const cached = machineCache.get(id);
    if (cached) return cached;
    if (story.translation_mode === 'machine' && story.title) {
      const translated = {title: story.title, body: story.body || ''};
      machineCache.set(id, translated);
      return translated;
    }
    return null;
  }

  function cardMarkup(story) {
    const id = storyId(story);
    const source = String(story.source || 'منبع').trim();
    const sourceUrl = safeUrl(story.source_url);
    const originalTitle = String(story.original_title || '').trim();
    const originalBody = String(story.original_body || '').trim();
    const machine = machineFor(story);
    const luna = lunaCache.get(id);
    const machineBusy = machineInFlight.has(id);
    const machineFailed = machineFailures.has(id);
    const priority = ['high', 'critical', 'breaking'].includes(String(story.priority || '').toLowerCase());

    const machinePanel = machine
      ? `<div class="v4-copy-box v4-machine-copy">
          <div class="v4-copy-label"><span>ترجمه ماشینی</span><small>Google-first · فقط برای تصمیم‌گیری</small></div>
          <h4>${esc(machine.title)}</h4>
          ${machine.body ? `<p>${esc(machine.body)}</p>` : ''}
        </div>`
      : `<div class="v4-copy-box v4-machine-copy is-empty">
          <div class="v4-copy-label"><span>ترجمه ماشینی</span><small>هنوز آماده نشده</small></div>
          ${machineFailed ? '<p class="v4-error-copy">خطا در آماده‌سازی ترجمه ماشینی؛ دوباره امتحان کن.</p>' : ''}
          <button class="v4-inline-btn" type="button" data-action="machine" ${machineBusy ? 'disabled' : ''}>${machineBusy ? 'در حال ترجمه…' : 'ترجمه ماشینی'}</button>
        </div>`;

    const lunaPanel = luna
      ? `<div class="v4-copy-box v4-luna-copy">
          <div class="v4-copy-label"><span>نسخه نهایی لونا</span><small>قبل از انتشار بررسی یا ویرایش کن</small></div>
          <h4>${esc(luna.title)}</h4>
          ${luna.body ? `<p>${esc(luna.body)}</p>` : ''}
        </div>`
      : `<div class="v4-copy-box v4-luna-copy is-empty">
          <div class="v4-copy-label"><span>لونا</span><small>هنوز استفاده نشده · توکن مصرف نشده</small></div>
        </div>`;

    return `<article class="v4-story-card${priority ? ' is-priority' : ''}" data-story-id="${esc(id)}">
      <header class="v4-story-head">
        <div class="v4-source-line">
          ${priority ? '<span class="v4-priority">مهم</span>' : ''}
          <strong>${esc(source)}</strong>
          <time>${esc(relativeTime(story.updated_at || story.published_at_source))}</time>
        </div>
        <span class="v4-story-status">${esc(story.panel_status_fa || 'تازه')}</span>
      </header>

      <div class="v4-original-copy">
        <div class="v4-copy-label"><span>متن اصلی منبع</span></div>
        <h3>${esc(originalTitle || 'بدون عنوان')}</h3>
        ${originalBody ? `<p>${esc(originalBody)}</p>` : ''}
      </div>

      ${machinePanel}
      ${lunaPanel}

      <div class="v4-story-actions">
        <button class="v4-action machine" type="button" data-action="machine" ${machineBusy ? 'disabled' : ''}>ترجمه ماشینی</button>
        <button class="v4-action luna" type="button" data-action="luna">ترجمه و ویراستاری با لونا</button>
        <button class="v4-action edit-luna" type="button" data-action="edit-luna" ${luna ? '' : 'disabled'}>ویرایش نسخه لونا</button>
        <button class="v4-action publish" type="button" data-action="publish-prepared" ${luna ? '' : 'disabled'}>انتشار نسخه لونا</button>
        <button class="v4-action reject" type="button" data-action="reject">رد</button>
        ${sourceUrl ? `<a class="v4-action source" href="${esc(sourceUrl)}" target="_blank" rel="noopener">منبع</a>` : ''}
      </div>
      <div class="v4-story-progress" aria-live="polite"></div>
    </article>`;
  }

  function renderFeed() {
    const visible = stories.slice(0, visibleCount);
    if (!visible.length) {
      feed.innerHTML = '<div class="v4-empty">فعلاً خبر تازه‌ای در فید نیست.</div>';
      if (loadMore) loadMore.hidden = true;
      return;
    }
    feed.innerHTML = visible.map(cardMarkup).join('');
    if (loadMore) loadMore.hidden = stories.length <= visibleCount;
    if (fields.live) fields.live.textContent = Number(stories.length).toLocaleString('fa-IR');
  }

  function updateStatus(status) {
    if (fields.engine) fields.engine.textContent = status.engine === 'v3' ? 'V3 فعال' : (status.engine || '—');
    if (fields.cycle) fields.cycle.textContent = relativeTime(status.last_cycle_at) || '—';
    if (fields.published) fields.published.textContent = Number(status.daily_published || 0).toLocaleString('fa-IR');
    if (fields.dailyLimit) fields.dailyLimit.textContent = Number(status.daily_limit || 35).toLocaleString('fa-IR');
    if (fields.dailyRemaining) fields.dailyRemaining.textContent = `${Number(status.daily_remaining || 0).toLocaleString('fa-IR')} خبر تا سهمیه امروز باقی مانده`;
    if (fields.dailyInput && document.activeElement !== fields.dailyInput) fields.dailyInput.value = Number(status.daily_limit || 35);
    if (fields.ready) fields.ready.textContent = Number(status.ready || 0).toLocaleString('fa-IR');
    if (fields.waiting) fields.waiting.textContent = Number(status.waiting || 0).toLocaleString('fa-IR');
    if (fields.specialPublished) fields.specialPublished.textContent = Number(status.special_published || 0).toLocaleString('fa-IR');
    if (fields.specialLimit) fields.specialLimit.textContent = Number(status.special_limit || 5).toLocaleString('fa-IR');
    if (fields.sourcesOk) fields.sourcesOk.textContent = Number(status.sources_ok || 0).toLocaleString('fa-IR');
    if (fields.sourcesFailed) fields.sourcesFailed.textContent = Number(status.sources_failed || 0).toLocaleString('fa-IR');
    if (fields.fetched) fields.fetched.textContent = Number(status.items_fetched || 0).toLocaleString('fa-IR');
    if (fields.reason) fields.reason.textContent = status.reason || '—';
    if (fields.error) fields.error.textContent = status.error || 'بدون خطا';
    window.dispatchEvent(new CustomEvent('newsroom:v4-status', {detail: status}));
  }

  async function machineTranslate(ids, {silent = false} = {}) {
    const wanted = [...new Set(ids.map(String).filter(Boolean))]
      .filter(id => !machineCache.has(id) && !machineInFlight.has(id));
    if (!wanted.length) return;
    wanted.forEach(id => { machineInFlight.add(id); machineFailures.delete(id); });
    renderFeed();
    try {
      const headers = UI.csrfHeaders ? UI.csrfHeaders({'Content-Type':'application/json'}) : {'Content-Type':'application/json'};
      const response = await fetch('/api/live-feed/machine-translate', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', headers,
        body: JSON.stringify({ids: wanted.slice(0, 6)}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
      const received = new Set();
      (Array.isArray(payload.items) ? payload.items : []).forEach(item => {
        const id = storyId(item);
        if (!id) return;
        machineCache.set(id, {title: String(item.title || ''), body: String(item.body || '')});
        machineFailures.delete(id);
        received.add(id);
      });
      wanted.forEach(id => { if (!received.has(id)) machineFailures.add(id); });
    } catch (error) {
      wanted.forEach(id => machineFailures.add(id));
      if (!silent) UI.toast?.('ترجمه ماشینی آماده نشد؛ متن اصلی همچنان قابل مشاهده است.', 'error');
    } finally {
      wanted.forEach(id => machineInFlight.delete(id));
      renderFeed();
    }
  }

  async function refresh({force = false} = {}) {
    if (controller) controller.abort();
    controller = new AbortController();
    try {
      const [feedResponse, statusResponse] = await Promise.all([
        fetch('/api/live-feed', {credentials:'same-origin', cache:'no-store', signal:controller.signal}),
        fetch('/api/newsroom/v4/status', {credentials:'same-origin', cache:'no-store', signal:controller.signal}),
      ]);
      if (!feedResponse.ok) throw new Error(`feed:${feedResponse.status}`);
      if (!statusResponse.ok) throw new Error(`status:${statusResponse.status}`);
      const feedPayload = await feedResponse.json();
      const status = await statusResponse.json();
      const nextStories = Array.isArray(feedPayload.items) ? feedPayload.items : [];
      const changed = force || JSON.stringify(nextStories.map(storyId)) !== JSON.stringify(stories.map(storyId));
      stories = nextStories;
      updateStatus(status);
      if (changed || firstPaint) renderFeed();
      firstPaint = false;

      const autoIds = stories.slice(0, 4).filter(s => s.needs_machine_translation || s.needs_localization).map(storyId);
      if (autoIds.length) void machineTranslate(autoIds, {silent:true});
    } catch (error) {
      if (error.name !== 'AbortError') UI.toast?.('به‌روزرسانی فید ناموفق بود.', 'error');
    } finally {
      controller = null;
      schedule();
    }
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => refresh(), document.hidden ? 60000 : 15000);
  }

  feed.addEventListener('click', event => {
    const button = event.target.closest('[data-action="machine"]');
    if (!button) return;
    event.preventDefault();
    const card = button.closest('[data-story-id]');
    if (card?.dataset.storyId) void machineTranslate([card.dataset.storyId]);
  });

  loadMore?.addEventListener('click', () => {
    visibleCount += 10;
    renderFeed();
  });
  refreshButton?.addEventListener('click', () => refresh({force:true}));
  document.addEventListener('visibilitychange', () => {
    window.clearTimeout(timer);
    if (!document.hidden) void refresh({force:false}); else schedule();
  });
  window.addEventListener('newsroom:refresh', () => refresh({force:true}));
  window.addEventListener('newsroom:luna-ready', event => {
    const detail = event.detail || {};
    if (!detail.id || !detail.title) return;
    lunaCache.set(String(detail.id), {title:String(detail.title), body:String(detail.body || '')});
    renderFeed();
  });
  window.addEventListener('newsroom:story-published', event => {
    const id = String(event.detail?.id || '');
    if (!id) return;
    stories = stories.filter(story => storyId(story) !== id);
    machineCache.delete(id);
    lunaCache.delete(id);
    renderFeed();
    void refresh({force:false});
  });
  window.addEventListener('newsroom:story-rejected', event => {
    const id = String(event.detail?.id || '');
    stories = stories.filter(story => storyId(story) !== id);
    renderFeed();
  });

  window.BikhabarV4 = {
    refresh,
    getLuna(id) { return lunaCache.get(String(id)) || null; },
    setLuna(id, title, body) {
      lunaCache.set(String(id), {title:String(title || ''), body:String(body || '')});
      renderFeed();
    },
    story(id) { return stories.find(item => storyId(item) === String(id)) || null; },
  };

  void refresh({force:true});
})();
