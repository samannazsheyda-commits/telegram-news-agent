(() => {
  const feed = document.getElementById('v4LiveFeed');
  if (!feed || !window.BikhabarV4) return;
  const V4 = window.BikhabarV4;
  const terminalPublished = new Set(['auto_published', 'published_auto', 'published_manual', 'reconciled_published']);
  const knownStoryIds = new Set(
    Array.from(feed.querySelectorAll('[data-story-id]'))
      .map(card => String(card.dataset.storyId || ''))
      .filter(Boolean)
  );
  let audioContext = null;
  let audioUnlocked = false;
  let refreshRunning = false;
  let reloadScheduled = false;

  function progress(card, text, kind = '') {
    const node = card?.querySelector('[data-v4-story-progress]');
    if (!node) return;
    node.hidden = !text;
    node.textContent = text || '';
    node.className = `v4-story-progress ${kind}`.trim();
  }

  function sourceLinkClone(actions) {
    return actions?.querySelector('.v41-source-link')?.cloneNode(true) || null;
  }

  function actionButton(label, action, kind = 'secondary') {
    const button = document.createElement('button');
    button.className = `v4-button v4-button-${kind}`;
    button.type = 'button';
    button.dataset.v4Action = action;
    button.textContent = label;
    return button;
  }

  function renderTranslation(card, result) {
    const panel = card?.querySelector('[data-v41-translation]');
    const actions = card?.querySelector('.v41-story-actions');
    if (!panel || !actions || !result?.quality_passed) return;
    panel.replaceChildren();

    const label = document.createElement('div');
    label.className = 'v41-translation-label';
    const labelMain = document.createElement('span');
    labelMain.textContent = 'نسخه Luna';
    const labelState = document.createElement('small');
    labelState.textContent = result.repaired ? 'کنترل کیفیت: تأیید پس از اصلاح' : 'کنترل کیفیت: تأیید';
    label.append(labelMain, labelState);
    panel.appendChild(label);

    const title = document.createElement('h3');
    title.dataset.v41Title = '1';
    title.textContent = result.title_fa || '';
    panel.appendChild(title);
    if (result.body_fa) {
      const body = document.createElement('p');
      body.dataset.v41Body = '1';
      body.textContent = result.body_fa;
      panel.appendChild(body);
    }

    const sourceLink = sourceLinkClone(actions);
    actions.replaceChildren();
    if (card.dataset.machineReady === '1') {
      actions.appendChild(actionButton('انتشار مستقیم', 'publish-machine', 'primary'));
    }
    actions.appendChild(actionButton('ترجمه دوباره', 'translate-luna'));
    actions.appendChild(actionButton('انتشار نسخه Luna', 'publish-luna', 'primary'));
    actions.appendChild(actionButton('بررسی / ویرایش', 'edit-final'));
    actions.appendChild(actionButton('رد و مسدودکردن', 'reject-block', 'danger'));
    if (sourceLink) actions.appendChild(sourceLink);
    card.dataset.finalReady = '1';
  }

  async function poll(commandId, card) {
    const started = Date.now();
    while (Date.now() - started < 45000) {
      const result = await V4.requestJSON(`/api/newsroom/command/${encodeURIComponent(commandId)}`);
      if (result.status === 'queued' || result.status === 'processing') {
        progress(card, result.status === 'queued' ? 'در صف انتشار…' : 'در حال انتشار…');
        await new Promise(resolve => window.setTimeout(resolve, 900));
        continue;
      }
      if (result.status === 'succeeded' || result.status === 'reconciled') return result;
      throw new Error(result.message || result.error || 'فرمان انتشار ناموفق بود');
    }
    throw new Error('پاسخ انتشار دیرتر از حد انتظار شد؛ وضعیت را دوباره بررسی کن');
  }

  async function translateWithLuna(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    card.classList.add('is-busy');
    progress(card, 'Luna در حال ترجمه و کنترل نام‌ها، اعداد و معنی خبر…');
    try {
      const result = await V4.requestJSON(`/api/panel/luna/translate-story/${encodeURIComponent(id)}`, {method: 'POST'});
      renderTranslation(card, result);
      progress(card, result.repaired ? 'ترجمه پس از یک اصلاح خودکار تأیید شد' : 'ترجمه تأیید شد', 'success');
      V4.toast('نسخه Luna آماده است.', 'success');
    } catch (error) {
      progress(card, error.message || 'ترجمه نیاز به بررسی دارد', 'error');
      V4.toast(error.message || 'ترجمه Luna تأیید نشد.', 'error');
    } finally {
      card.classList.remove('is-busy');
    }
  }

  async function moveToReview(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    card.classList.add('is-busy');
    progress(card, 'در حال انتقال نسخه فعلی به ویرایش…');
    try {
      const result = await V4.requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/review`, {method: 'POST'});
      window.location.href = result.review_url || `/review/${encodeURIComponent(id)}`;
    } catch (error) {
      card.classList.remove('is-busy');
      progress(card, error.message, 'error');
      V4.toast(error.message, 'error');
    }
  }

  function copyPreview(card, mode) {
    const titleSelector = mode === 'luna' ? '[data-v41-title]' : '[data-v41-publish-title]';
    const bodySelector = mode === 'luna' ? '[data-v41-body]' : '[data-v41-publish-body]';
    const title = card.querySelector(titleSelector)?.textContent?.trim() || '';
    const body = card.querySelector(bodySelector)?.textContent?.trim() || '';
    return [title, body].filter(Boolean).join('\n\n');
  }

  async function publishCopy(card, mode) {
    const id = card?.dataset.storyId;
    const ready = mode === 'luna' ? card?.dataset.finalReady === '1' : card?.dataset.machineReady === '1';
    if (!id || !ready || card.classList.contains('is-busy')) return;
    const preview = copyPreview(card, mode);
    const label = mode === 'luna' ? 'نسخه Luna' : 'ترجمه ماشینی';
    const accepted = await V4.confirmAction({
      title: `${label} منتشر شود؟`,
      text: preview.length > 700 ? `${preview.slice(0, 700)}…` : preview,
      accept: 'تأیید و انتشار',
    });
    if (!accepted) return;

    card.classList.add('is-busy');
    progress(card, 'نسخه‌ای که دیدی در صف امن انتشار قرار می‌گیرد…');
    try {
      const url = mode === 'machine'
        ? `/api/panel/luna/publish-machine/${encodeURIComponent(id)}`
        : `/api/panel/luna/publish-final/${encodeURIComponent(id)}`;
      const options = mode === 'luna'
        ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({copy_mode: 'luna'})}
        : {method: 'POST'};
      const queued = await V4.requestJSON(url, options);
      const done = await poll(queued.command_id, card);
      progress(card, done.telegram_message_id ? `منتشر شد · Message ID ${done.telegram_message_id}` : 'منتشر شد', 'success');
      V4.toast('خبر منتشر شد.', 'success');
      card.remove();
    } catch (error) {
      progress(card, error.message, 'error');
      V4.toast(error.message, 'error');
    } finally {
      if (card.isConnected) card.classList.remove('is-busy');
    }
  }

  async function rejectAndBlock(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    const accepted = await V4.confirmAction({
      title: 'این خبر برای همیشه از چرخه انتشار خارج شود؟',
      text: 'خبر رد می‌شود و Block آن ثبت می‌شود تا در چرخه‌های بعدی دوباره Ready نشود.',
      accept: 'رد و مسدودکردن',
    });
    if (!accepted) return;
    card.classList.add('is-busy');
    try {
      await V4.requestJSON(`/api/panel/luna/block-story/${encodeURIComponent(id)}`, {method: 'POST'});
      card.remove();
      V4.toast('خبر رد و مسدود شد.', 'success');
    } catch (error) {
      card.classList.remove('is-busy');
      progress(card, error.message, 'error');
      V4.toast(error.message, 'error');
    }
  }

  function playNewStoryAlarm() {
    if (!audioUnlocked || !audioContext) {
      try { window.sessionStorage.setItem('bikhabar-pending-news-alarm', '1'); } catch (_error) {}
      return;
    }
    try { window.sessionStorage.removeItem('bikhabar-pending-news-alarm'); } catch (_error) {}
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.12, audioContext.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.18);
    oscillator.connect(gain).connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.2);
  }

  function unlockNewsroomAudio() {
    if (audioUnlocked) return;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    audioContext = audioContext || new AudioContextClass();
    Promise.resolve(audioContext.resume()).then(() => {
      audioUnlocked = true;
      let pending = false;
      try { pending = window.sessionStorage.getItem('bikhabar-pending-news-alarm') === '1'; } catch (_error) {}
      if (pending) playNewStoryAlarm();
    }).catch(() => {});
  }

  document.addEventListener('pointerdown', unlockNewsroomAudio, {once: true});
  document.addEventListener('keydown', unlockNewsroomAudio, {once: true});

  function newStoryIds(items) {
    const fresh = [];
    items.forEach(item => {
      const id = String(item.id || item.item_id || '');
      if (!id) return;
      const status = String(item.panel_status || '');
      if (!knownStoryIds.has(id) && !terminalPublished.has(status)) fresh.push(id);
      knownStoryIds.add(id);
    });
    return fresh;
  }

  function removeTerminalPublishedCards(items) {
    items.forEach(item => {
      if (!terminalPublished.has(String(item.panel_status || ''))) return;
      const id = String(item.id || item.item_id || '');
      if (!id) return;
      const card = Array.from(feed.querySelectorAll('[data-story-id]'))
        .find(node => String(node.dataset.storyId || '') === id);
      if (card) card.remove();
    });
  }

  async function localizePending(items) {
    const ids = items
      .filter(item => item.needs_localization && !terminalPublished.has(String(item.panel_status || '')))
      .map(item => String(item.id || item.item_id || ''))
      .filter(Boolean)
      .slice(0, 12);
    if (!ids.length) return [];
    try {
      const payload = await V4.requestJSON('/api/live-feed/localize', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids}),
      });
      return Array.isArray(payload.items) ? payload.items : [];
    } catch (_error) {
      return [];
    }
  }

  function scheduleReload() {
    if (reloadScheduled) return;
    reloadScheduled = true;
    window.setTimeout(() => window.location.reload(), 450);
  }

  async function refreshLiveFeed() {
    if (refreshRunning) return;
    refreshRunning = true;
    try {
      const payload = await V4.requestJSON('/api/live-feed');
      const items = Array.isArray(payload.items) ? payload.items : [];
      removeTerminalPublishedCards(items);
      const freshIds = newStoryIds(items);
      if (freshIds.length) playNewStoryAlarm();
      const localized = await localizePending(items);
      if (freshIds.length || localized.length) scheduleReload();
    } catch (_error) {
      // Keep the current dashboard usable; the next poll retries naturally.
    } finally {
      refreshRunning = false;
    }
  }

  feed.addEventListener('click', event => {
    const target = event.target.closest('[data-v4-action]');
    if (!target) return;
    event.preventDefault();
    const card = target.closest('[data-story-id]');
    const action = target.dataset.v4Action;
    if (action === 'translate-luna') void translateWithLuna(card);
    if (action === 'edit-final') void moveToReview(card);
    if (action === 'publish-machine') void publishCopy(card, 'machine');
    if (action === 'publish-luna') void publishCopy(card, 'luna');
    if (action === 'reject-block') void rejectAndBlock(card);
  });

  window.setTimeout(refreshLiveFeed, 700);
  window.setInterval(refreshLiveFeed, 5000);
})();
