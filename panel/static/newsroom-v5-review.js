(() => {
  'use strict';

  const MAX_RENDERED_CARDS = 80;
  const PAGE_SIZE = 25;

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
  }

  function ageLabel(seconds) {
    if (seconds === null || seconds === undefined) return '';
    if (seconds < 60) return 'همین حالا';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} دقیقه پیش`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} ساعت پیش`;
    return `${Math.floor(hours / 24)} روز پیش`;
  }

  function timeLabel(value) {
    if (!value) return '';
    try {
      return new Intl.DateTimeFormat('fa-IR', {
        hour: '2-digit', minute: '2-digit', year: 'numeric', month: '2-digit', day: '2-digit'
      }).format(new Date(value));
    } catch (_) {
      return String(value);
    }
  }

  function requestId(storyId) {
    if (window.crypto?.randomUUID) return `publish:${storyId}:${window.crypto.randomUUID()}`;
    return `publish:${storyId}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
  }

  class ReviewController {
    constructor(options = {}) {
      this.list = document.getElementById(options.listId || 'v5ReviewList');
      this.sentinel = document.getElementById(options.sentinelId || 'v5ReviewSentinel');
      this.empty = document.getElementById(options.emptyId || 'v5ReviewEmpty');
      this.items = [];
      this.byId = new Map();
      this.nextCursor = null;
      this.loading = false;
      this.exhausted = false;
      this.busyStoryIds = new Set();
      this.onToast = options.onToast || (() => {});
      this.onCountsChanged = options.onCountsChanged || (() => {});
      this.observer = null;
    }

    start() {
      if (!this.list || !this.sentinel) return;
      this.list.addEventListener('click', event => this.onClick(event));
      this.observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) this.loadMore();
      }, { rootMargin: '800px 0px' });
      this.observer.observe(this.sentinel);
      this.loadFirst();
    }

    async fetchPage(cursor = null) {
      const url = new URL('/api/v5/review', window.location.origin);
      url.searchParams.set('limit', String(PAGE_SIZE));
      if (cursor) url.searchParams.set('cursor', cursor);
      const response = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`review_http_${response.status}`);
      return response.json();
    }

    async loadFirst() {
      if (this.loading) return;
      this.loading = true;
      try {
        const page = await this.fetchPage();
        this.items = [];
        this.byId.clear();
        this.mergeItems(page.items || [], false);
        this.nextCursor = page.next_cursor || null;
        this.exhausted = !this.nextCursor;
        this.render();
      } catch (error) {
        this.onToast('گرفتن فهرست خبرها ناموفق بود. دوباره تلاش می‌کنم.', 'error');
      } finally {
        this.loading = false;
      }
    }

    async loadMore() {
      if (this.loading || this.exhausted || !this.nextCursor) return;
      this.loading = true;
      try {
        const page = await this.fetchPage(this.nextCursor);
        this.mergeItems(page.items || [], true);
        this.nextCursor = page.next_cursor || null;
        this.exhausted = !this.nextCursor;
        this.render();
      } catch (_) {
        this.onToast('بارگذاری خبرهای بعدی ناموفق بود.', 'error');
      } finally {
        this.loading = false;
      }
    }

    mergeItems(incoming, append) {
      const fresh = [];
      for (const item of incoming) {
        if (!item?.id || !item.title_fa) continue;
        this.byId.set(item.id, item);
        fresh.push(item);
      }
      if (append) {
        const seen = new Set(this.items.map(item => item.id));
        this.items.push(...fresh.filter(item => !seen.has(item.id)));
      } else {
        const incomingIds = new Set(fresh.map(item => item.id));
        this.items = [...fresh, ...this.items.filter(item => !incomingIds.has(item.id))];
      }
      this.items.sort((a, b) => {
        const time = String(b.published_at_source || '').localeCompare(String(a.published_at_source || ''));
        return time || String(b.id).localeCompare(String(a.id));
      });
    }

    visibleItems() {
      if (this.items.length <= MAX_RENDERED_CARDS) return this.items;
      return this.items.slice(this.items.length - MAX_RENDERED_CARDS);
    }

    render() {
      const items = this.visibleItems();
      this.list.innerHTML = items.map(item => this.cardHtml(item)).join('');
      if (this.empty) this.empty.hidden = this.items.length !== 0;
    }

    cardHtml(item) {
      const priority = escapeHtml(item.priority_class || 'normal');
      const busy = this.busyStoryIds.has(item.id);
      return `
        <article class="v5-story-card${busy ? ' is-busy' : ''}" data-story-id="${escapeHtml(item.id)}">
          <div class="v5-story-meta">
            <span class="v5-source">${escapeHtml(item.source_name || 'منبع')}</span>
            <span>${escapeHtml(timeLabel(item.published_at_source))}</span>
            <span>${escapeHtml(ageLabel(item.age_seconds))}</span>
            <span class="v5-priority" data-priority="${priority}">${priority}</span>
          </div>
          <h2>${escapeHtml(item.title_fa)}</h2>
          ${item.body_fa ? `<p class="v5-story-body">${escapeHtml(item.body_fa)}</p>` : ''}
          ${item.editorial_reason ? `<p class="v5-editorial-reason">Luna: ${escapeHtml(item.editorial_reason)}</p>` : ''}
          <div class="v5-story-actions">
            <button type="button" class="v5-primary" data-action="publish" ${busy ? 'disabled' : ''}>انتشار</button>
            <button type="button" data-action="edit" ${busy ? 'disabled' : ''}>ویرایش</button>
            <button type="button" data-action="reject" class="v5-danger" ${busy ? 'disabled' : ''}>رد خبر</button>
            <button type="button" data-action="luna">از Luna بپرس</button>
            ${item.source_url ? `<button type="button" data-action="source">منبع</button>` : ''}
          </div>
        </article>`;
    }

    async onClick(event) {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const card = button.closest('[data-story-id]');
      const item = this.byId.get(card?.dataset.storyId);
      if (!item) return;
      const action = button.dataset.action;
      if (action === 'publish') await this.confirmPublish(item);
      else if (action === 'reject') await this.confirmReject(item);
      else if (action === 'edit') await this.edit(item);
      else if (action === 'luna') window.dispatchEvent(new CustomEvent('v5:luna-story', { detail: { story: item } }));
      else if (action === 'source' && item.source_url) window.open(item.source_url, '_blank', 'noopener,noreferrer');
    }

    async confirmPublish(item) {
      if (this.busyStoryIds.has(item.id)) return;
      const confirmed = await window.NewsroomV5.confirm({
        title: 'انتشار این خبر؟',
        text: 'همین نسخه فارسی برای صف انتشار ثبت می‌شود.',
        preview: `${item.title_fa}${item.body_fa ? `\n\n${item.body_fa}` : ''}`,
        danger: false,
      });
      if (!confirmed) return;
      const key = requestId(item.id);
      await this.mutate(item.id, async () => {
        const response = await fetch(`/api/v5/story/${encodeURIComponent(item.id)}/publish`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
            'Idempotency-Key': key,
          },
          body: JSON.stringify({ confirmed: true }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || `publish_http_${response.status}`);
        this.remove(item.id);
        this.onToast('خبر وارد صف انتشار شد.', 'success');
        this.onCountsChanged();
      });
    }

    async confirmReject(item) {
      if (this.busyStoryIds.has(item.id)) return;
      const confirmed = await window.NewsroomV5.confirm({
        title: 'رد این خبر؟',
        text: 'همین خبر دیگر با اسکن بعدی برنمی‌گردد؛ منبع مسدود نمی‌شود.',
        preview: item.title_fa,
        danger: true,
      });
      if (!confirmed) return;
      await this.mutate(item.id, async () => {
        const response = await fetch(`/api/v5/story/${encodeURIComponent(item.id)}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
          body: JSON.stringify({ confirmed: true }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || `reject_http_${response.status}`);
        this.remove(item.id);
        this.onToast('خبر رد شد.', 'success');
        this.onCountsChanged();
      });
    }

    async edit(item) {
      const title = window.prompt('تیتر فارسی نهایی', item.title_fa || '');
      if (title === null) return;
      const body = window.prompt('متن فارسی نهایی', item.body_fa || '');
      if (body === null) return;
      await this.mutate(item.id, async () => {
        const response = await fetch(`/api/v5/story/${encodeURIComponent(item.id)}/copy`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
          body: JSON.stringify({ title_fa: title, body_fa: body }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || `edit_http_${response.status}`);
        this.byId.set(item.id, payload);
        this.items = this.items.map(row => row.id === item.id ? payload : row);
        this.render();
        this.onToast('نسخه فارسی ذخیره شد.', 'success');
      });
    }

    async mutate(storyId, task) {
      this.busyStoryIds.add(storyId);
      this.render();
      try {
        await task();
      } catch (_) {
        this.onToast('عملیات انجام نشد؛ خبر سر جایش ماند.', 'error');
      } finally {
        this.busyStoryIds.delete(storyId);
        this.render();
      }
    }

    remove(storyId) {
      this.byId.delete(storyId);
      this.items = this.items.filter(item => item.id !== storyId);
      this.render();
    }

    async refreshTop() {
      if (this.loading) return;
      try {
        const page = await this.fetchPage();
        this.mergeItems(page.items || [], false);
        this.render();
      } catch (_) {}
    }

    onRealtime(type, payload) {
      const storyId = payload?.story_id;
      if ((type === 'story_rejected' || type === 'story_published') && storyId) this.remove(storyId);
      else if (type === 'story_added' || type === 'story_updated' || type === 'refetch_required') this.refreshTop();
    }
  }

  window.NewsroomV5Review = { ReviewController, MAX_RENDERED_CARDS };
})();
