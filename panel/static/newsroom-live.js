(() => {
  if (!document.getElementById('liveFeed')) return;
  const UI = window.BikhabarUI || {};
  const feed = document.getElementById('liveFeed');
  const newNewsBadge = document.getElementById('newNewsBadge');
  const fields = {
    engine: document.getElementById('engineState'),
    telegram: document.getElementById('telegramState'),
    publishing: document.getElementById('publishingState'),
    cycle: document.getElementById('lastCycleAt'),
    live: document.getElementById('liveCount'),
    review: document.getElementById('reviewCount'),
    published: document.getElementById('publishedCount'),
    rejected: document.getElementById('rejectedCount'),
    reason: document.getElementById('cycleReason'),
    ok: document.getElementById('sourcesOk'),
    failed: document.getElementById('sourcesFailed'),
    fetched: document.getElementById('itemsFetched'),
    messageId: document.getElementById('telegramMessageId'),
    error: document.getElementById('lastError'),
    healthDot: document.getElementById('healthDot'),
    priorities: document.getElementById('priorityList'),
  };
  let fingerprint = '';
  let controller = null;
  let timer = 0;
  let badgeTimer = 0;
  let initial = true;
  let knownIds = new Set([...feed.querySelectorAll('[data-story-id]')].map(node => node.dataset.storyId));

  const esc = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function safeUrl(value) {
    try {
      const url = new URL(String(value || ''), window.location.origin);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch (_) { return ''; }
  }

  function setState(node, text, state = '') {
    if (!node) return;
    node.textContent = text;
    node.classList.remove('nr-state-ok', 'nr-state-bad', 'nr-state-warn');
    if (state) node.classList.add(`nr-state-${state}`);
  }

  function storyCard(story, isNew) {
    const id = esc(story.id);
    const title = esc(story.title || 'بدون عنوان');
    const body = esc(story.body || '');
    const source = esc(story.source || 'منبع');
    const url = safeUrl(story.source_url);
    const priority = ['high','critical','breaking','manual'].includes(String(story.priority || '').toLowerCase());
    const status = esc(story.status || 'new');
    const relative = esc(UI.relativeTime ? UI.relativeTime(story.discovered_at) : '');
    return `<article class="nr-story-card${priority ? ' is-priority' : ''}${isNew ? ' is-new' : ''}"
      data-story-id="${id}" data-news-id="${id}" data-story-title="${title}" data-story-body="${body}"
      data-story-source="${source}" data-story-source-url="${esc(url)}">
      <input class="live-select" type="checkbox" value="${id}" aria-label="انتخاب خبر">
      <div class="nr-story-rail"></div>
      <div class="nr-story-head"><div class="nr-story-meta">
        ${priority ? '<span class="nr-priority-badge">مهم</span>' : ''}<span>${source}</span><time>${relative}</time>
      </div><span class="nr-story-status">${status}</span></div>
      <h3>${title}</h3>${body ? `<p>${body}</p>` : ''}
      <div class="nr-story-actions">
        <button class="nr-story-action publish" type="button" data-action="publish">انتشار</button>
        <button class="nr-story-action" type="button" data-action="edit">ویرایش</button>
        <button class="nr-story-action reject" type="button" data-action="reject">رد</button>
        ${url ? `<a class="nr-story-action source" data-action="source" href="${esc(url)}" target="_blank" rel="noopener">منبع</a>` : '<span></span>'}
      </div><div class="nr-story-progress" hidden></div>
    </article>`;
  }

  function showNewNewsBadge(count) {
    if (!newNewsBadge || count <= 0) return;
    newNewsBadge.textContent = count > 1 ? `${count.toLocaleString('fa-IR')} خبر جدید` : 'خبر جدید';
    newNewsBadge.hidden = false;
    window.clearTimeout(badgeTimer);
    badgeTimer = window.setTimeout(() => { newNewsBadge.hidden = true; }, 5000);
  }

  function renderFeed(stories) {
    if (!Array.isArray(stories) || stories.length === 0) {
      feed.innerHTML = '<div class="nr-empty"><span>◌</span><strong>فعلاً خبر تازه‌ای نیست</strong><small>فید به‌صورت خودکار به‌روز می‌شود.</small></div>';
      knownIds = new Set();
      window.dispatchEvent(new Event('newsroom:feed-rendered'));
      return;
    }
    let importantNew = false;
    let newCount = 0;
    const nextIds = new Set(stories.map(story => String(story.id || '')));
    feed.innerHTML = stories.map(story => {
      const id = String(story.id || '');
      const isNew = !initial && id && !knownIds.has(id);
      if (isNew) newCount += 1;
      if (isNew && ['high','critical','breaking'].includes(String(story.priority || '').toLowerCase())) importantNew = true;
      return storyCard(story, isNew);
    }).join('');
    knownIds = nextIds;
    if (newCount) showNewNewsBadge(newCount);
    if (importantNew && UI.ping) UI.ping();
    window.dispatchEvent(new Event('newsroom:feed-rendered'));
  }

  function render(snapshot) {
    const v3 = snapshot.v3 || {};
    const engineOk = snapshot.engine === 'v3';
    setState(fields.engine, snapshot.engine === 'v3' ? 'V3 فعال' : (snapshot.engine || 'نامشخص'), engineOk ? 'ok' : 'warn');
    setState(fields.telegram, snapshot.telegram_state === 'ok' ? 'سالم' : (snapshot.telegram_state === 'error' ? 'خطا' : 'نامشخص'), snapshot.telegram_state === 'ok' ? 'ok' : (snapshot.telegram_state === 'error' ? 'bad' : 'warn'));
    setState(fields.publishing, snapshot.publishing ? 'فعال' : 'متوقف', snapshot.publishing ? 'ok' : 'bad');
    if (fields.cycle) fields.cycle.textContent = UI.relativeTime ? UI.relativeTime(v3.last_cycle_at) : (v3.last_cycle_at || '—');
    if (fields.live) fields.live.textContent = Number(snapshot.counts?.live || 0).toLocaleString('fa-IR');
    if (fields.review) fields.review.textContent = Number(snapshot.counts?.review || 0).toLocaleString('fa-IR');
    if (fields.published) fields.published.textContent = Number(snapshot.counts?.published || 0).toLocaleString('fa-IR');
    if (fields.rejected) fields.rejected.textContent = Number(snapshot.counts?.rejected || 0).toLocaleString('fa-IR');
    if (fields.reason) fields.reason.textContent = v3.reason || '—';
    if (fields.ok) fields.ok.textContent = Number(v3.sources_ok || 0).toLocaleString('fa-IR');
    if (fields.failed) fields.failed.textContent = Number(v3.sources_failed || 0).toLocaleString('fa-IR');
    if (fields.fetched) fields.fetched.textContent = Number(v3.items_fetched || 0).toLocaleString('fa-IR');
    if (fields.messageId) fields.messageId.textContent = v3.telegram_message_id ? Number(v3.telegram_message_id).toLocaleString('fa-IR') : '—';
    if (fields.error) fields.error.textContent = v3.error || 'بدون خطا';
    if (fields.healthDot) fields.healthDot.className = `nr-health-dot ${engineOk && !v3.error ? 'is-ok' : 'is-bad'}`;
    if (fields.priorities) fields.priorities.innerHTML = (snapshot.settings?.priority_terms || []).map(term => `<span>${esc(term)}</span>`).join('') || '<span>بدون اولویت اختصاصی</span>';
    renderFeed(snapshot.live || []);
  }

  async function refresh({force = false} = {}) {
    if (controller) controller.abort();
    controller = new AbortController();
    try {
      const response = await fetch('/api/newsroom/snapshot', {credentials:'same-origin', cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const snapshot = await response.json();
      window.BikhabarNewsroomSnapshot = snapshot;
      if (force || snapshot.fingerprint !== fingerprint) {
        render(snapshot);
        fingerprint = snapshot.fingerprint || '';
        window.dispatchEvent(new CustomEvent('newsroom:snapshot', {detail:snapshot}));
      }
      initial = false;
    } catch (error) {
      if (error.name !== 'AbortError') {
        setState(fields.engine, 'ارتباط قطع', 'bad');
        if (UI.toast) UI.toast('دریافت وضعیت اتاق خبر ناموفق بود.', 'error');
      }
    } finally {
      controller = null;
      schedule();
    }
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => refresh(), document.hidden ? 15000 : 3000);
  }

  document.addEventListener('visibilitychange', () => {
    window.clearTimeout(timer);
    refresh({force:false});
  });
  window.addEventListener('newsroom:refresh', () => refresh({force:true}));
  refresh({force:true});
})();
