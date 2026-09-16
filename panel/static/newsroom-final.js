(() => {
  const feed = document.getElementById('liveFeed');
  if (!feed) return;

  const fa = new Intl.NumberFormat('fa-IR');
  const SOURCE_LABELS = {
    'ClashReport / Telegram': 'کلش ریپورت / تلگرام',
    'Clash Report / Telegram': 'کلش ریپورت / تلگرام',
    'Clash Report': 'کلش ریپورت',
  };
  const REASON_FA = {
    attempt_limit: 'خبرهای آمادهٔ فعلی به سقف تلاش رسیده‌اند',
    final_gate_rejected: 'خبر در بررسی نهایی لونا تأیید نشد',
    final_gate_error: 'بررسی نهایی لونا موقتاً با خطا روبه‌رو شد',
    daily_limit: 'سقف انتشار روزانه تکمیل شده',
    publish_interval: 'فاصلهٔ امن بین انتشارها در حال رعایت است',
    no_safe_candidate: 'فعلاً خبر تازه و قابل انتشار در صف نیست',
    retry_cooldown: 'منتظر نوبت تلاش دوباره هستیم',
    ambiguous_remote_state: 'وضعیت ارسال قبلی نیازمند بررسی است',
    publish_paused: 'انتشار خودکار متوقف است',
    published: 'خبر منتشر شد',
    safe_candidate: 'خبر آمادهٔ بررسی نهایی است',
  };
  const FILTER_LABELS = {
    live: 'قابل اقدام',
    review: 'نیازمند بررسی',
    rejected: 'ردشده',
    published: 'منتشرشده',
  };
  const TERMINAL_PUBLISHED = new Set(['auto_published', 'published_auto', 'published_manual']);
  let activeFilter = 'live';
  let snapshot = null;

  function reasonFa(value) {
    const code = String(value || '').trim();
    if (!code) return '—';
    if (REASON_FA[code]) return REASON_FA[code];
    if (code.startsWith('duplicate_event')) return 'این رویداد قبلاً پوشش داده شده';
    if (code.startsWith('material_duplicate') || code.startsWith('duplicate_of_recent')) return 'این خبر تکراری تشخیص داده شد';
    if (code.includes('opinion') || code.includes('analysis_not_concrete')) return 'محتوا تحلیلی/نظری است، نه یک رویداد خبری مستقل';
    if (code === 'outside_selected_topics') return 'خارج از موضوعات انتخابی اتاق خبر';
    return 'وضعیت ثبت‌شده در جزئیات فنی';
  }

  function sectionFor(story) {
    const status = String(story?.panel_status || story?.status || '').toLowerCase();
    const reason = String(story?.decision_reason || '').toLowerCase();
    if (TERMINAL_PUBLISHED.has(status) || status.includes('published')) return 'published';
    if (status.includes('reject') || status === 'failed' || reason === 'outside_selected_topics' || reason.startsWith('final_gate:') || reason.startsWith('publisher:')) return 'rejected';
    if (status === 'waiting' || status.includes('review') || reason === 'needs_editorial_review') return 'review';
    return 'live';
  }

  function ensureShell() {
    if (document.getElementById('dailyCapacitySummary')) return;
    const kpis = document.querySelector('.nr-kpis');
    if (kpis) {
      const capacity = document.createElement('section');
      capacity.className = 'nr-capacity-strip';
      capacity.setAttribute('aria-label', 'ظرفیت انتشار امروز');
      capacity.innerHTML = `
        <div class="nr-capacity-copy">
          <span>ظرفیت انتشار امروز</span>
          <strong id="dailyCapacitySummary">در حال دریافت…</strong>
        </div>
        <div class="nr-capacity-track" aria-hidden="true"><i id="dailyCapacityBar"></i></div>
        <div class="nr-capacity-meta">
          <span>آخرین انتشار: <b id="lastPublishedAt">—</b></span>
          <span>منابع سالم: <b id="healthySourceSummary">—</b></span>
        </div>`;
      kpis.before(capacity);
    }

    const liveDesk = document.querySelector('.nr-live-desk');
    const toolbar = liveDesk?.querySelector('.nr-bulk-toolbar');
    if (liveDesk && toolbar) {
      const tabs = document.createElement('div');
      tabs.id = 'newsroomFeedTabs';
      tabs.className = 'nr-feed-tabs';
      tabs.setAttribute('role', 'tablist');
      tabs.innerHTML = ['live','review','rejected','published'].map(key =>
        `<button type="button" role="tab" data-feed-filter="${key}" aria-selected="${key === 'live' ? 'true' : 'false'}"><span>${FILTER_LABELS[key]}</span><b data-filter-count="${key}">۰</b></button>`
      ).join('');
      toolbar.before(tabs);
      tabs.addEventListener('click', event => {
        const button = event.target.closest('[data-feed-filter]');
        if (!button) return;
        activeFilter = button.dataset.feedFilter || 'live';
        tabs.querySelectorAll('[data-feed-filter]').forEach(node => node.setAttribute('aria-selected', String(node === button)));
        applyFeedFilter();
      });
    }

    const health = document.querySelector('.nr-health-list');
    if (health && !document.getElementById('technicalReasonCode')) {
      const details = document.createElement('details');
      details.className = 'nr-technical-details';
      details.innerHTML = '<summary>جزئیات فنی چرخه</summary><div><span>reason</span><code id="technicalReasonCode">—</code></div><div><span>error</span><code id="technicalErrorCode">—</code></div>';
      health.after(details);
    }
  }

  function storyMap() {
    return new Map((snapshot?.live || []).map(story => [String(story.id || story.item_id || ''), story]));
  }

  function updateCard(card, story) {
    const section = sectionFor(story);
    card.dataset.panelSection = section;
    const source = String(story?.source || '').trim();
    const sourceFa = SOURCE_LABELS[source];
    if (sourceFa) {
      const sourceNodes = [...card.querySelectorAll('.nr-story-meta span')].filter(node => !node.classList.contains('nr-priority-badge'));
      if (sourceNodes[0]) sourceNodes[0].textContent = sourceFa;
      card.dataset.storySource = sourceFa;
    }
    const actions = card.querySelector('.nr-story-actions');
    if (actions) {
      actions.querySelectorAll('[data-action="publish"],[data-action="edit"],[data-action="reject"]').forEach(node => {
        node.hidden = section === 'published' || section === 'rejected';
      });
    }
  }

  function currentCounts() {
    const counts = {live:0, review:0, rejected:0, published:0};
    (snapshot?.live || []).forEach(story => { counts[sectionFor(story)] += 1; });
    return counts;
  }

  function applyFeedFilter() {
    ensureShell();
    const map = storyMap();
    feed.querySelectorAll('[data-story-id]').forEach(card => {
      const story = map.get(String(card.dataset.storyId || '')) || {};
      updateCard(card, story);
      card.hidden = card.dataset.panelSection !== activeFilter;
    });
    const counts = currentCounts();
    document.querySelectorAll('[data-filter-count]').forEach(node => {
      const key = node.dataset.filterCount;
      const globalValue = key === 'published' ? snapshot?.counts?.published : key === 'rejected' ? snapshot?.counts?.rejected : null;
      node.textContent = fa.format(Number(globalValue ?? counts[key] ?? 0));
    });
    const heading = document.querySelector('.nr-live-desk .nr-section-head h2');
    if (heading) heading.textContent = FILTER_LABELS[activeFilter] || 'ورودی زنده';
    const visible = [...feed.querySelectorAll('[data-story-id]')].some(card => !card.hidden);
    let empty = feed.querySelector('.nr-filter-empty');
    if (!visible) {
      if (!empty) {
        empty = document.createElement('div');
        empty.className = 'nr-empty nr-filter-empty';
        feed.appendChild(empty);
      }
      const historyLink = activeFilter === 'published' || activeFilter === 'rejected'
        ? '<a href="/history">مشاهده تاریخچه کامل</a>' : '';
      empty.innerHTML = `<span>✓</span><strong>در این بخش موردی نیست</strong><small>${historyLink}</small>`;
      empty.hidden = false;
    } else if (empty) {
      empty.hidden = true;
    }
  }

  function updateSummary(next) {
    snapshot = next || {};
    ensureShell();
    const v3 = snapshot.v3 || {};
    const published = Number(v3.daily_published ?? snapshot.counts?.published ?? 0);
    const limit = Number(v3.daily_limit ?? 35) || 35;
    const remaining = Number(v3.daily_remaining ?? Math.max(0, limit - published));
    const summary = document.getElementById('dailyCapacitySummary');
    if (summary) summary.textContent = `${fa.format(published)} از ${fa.format(limit)} منتشر شده · ${fa.format(remaining)} ظرفیت باقی‌مانده`;
    const bar = document.getElementById('dailyCapacityBar');
    if (bar) bar.style.width = `${Math.min(100, Math.max(0, (published / limit) * 100))}%`;
    const lastPublished = document.getElementById('lastPublishedAt');
    if (lastPublished) lastPublished.textContent = v3.last_published_at ? (window.BikhabarUI?.relativeTime?.(v3.last_published_at) || v3.last_published_at) : '—';
    const healthy = document.getElementById('healthySourceSummary');
    if (healthy) healthy.textContent = fa.format(Number(v3.sources_ok || 0));

    const reason = String(v3.reason || '');
    const error = String(v3.error || '');
    const reasonNode = document.getElementById('cycleReason');
    if (reasonNode) reasonNode.textContent = reasonFa(reason);
    const errorNode = document.getElementById('lastError');
    if (errorNode) errorNode.textContent = error ? reasonFa(error) : 'بدون خطا';
    const reasonCode = document.getElementById('technicalReasonCode');
    if (reasonCode) reasonCode.textContent = reason || '—';
    const errorCode = document.getElementById('technicalErrorCode');
    if (errorCode) errorCode.textContent = error || '—';

    const healthDot = document.getElementById('healthDot');
    if (healthDot) {
      const healthySystem = snapshot.engine === 'v3' && snapshot.telegram_state !== 'error' && Number(v3.publish_failed || 0) === 0;
      healthDot.className = `nr-health-dot ${healthySystem ? 'is-ok' : 'is-bad'}`;
    }
    applyFeedFilter();
  }

  ensureShell();
  window.addEventListener('newsroom:snapshot', event => updateSummary(event.detail));
  window.addEventListener('newsroom:feed-rendered', () => applyFeedFilter());
  if (window.BikhabarNewsroomSnapshot) updateSummary(window.BikhabarNewsroomSnapshot);
})();
