(() => {
  const feed = document.getElementById('v4LiveFeed');
  if (!feed || !window.BikhabarV4) return;

  const V4 = window.BikhabarV4;
  const terminalStatuses = new Set([
    'auto_published',
    'published_auto',
    'published_manual',
    'reconciled_published',
    'rejected_manual',
    'blocked',
    'superseded',
  ]);
  const knownStoryIds = new Set(
    Array.from(feed.querySelectorAll('[data-story-id]'))
      .map(card => String(card.dataset.storyId || ''))
      .filter(Boolean)
  );

  const refreshButton = document.getElementById('v4RefreshLive');
  const soundButton = document.getElementById('v4SoundToggle');
  const refreshState = document.getElementById('v4RefreshState');
  let audioContext = null;
  let audioUnlocked = false;
  let refreshRunning = false;
  let initialSnapshotComplete = false;
  let soundEnabled = true;

  try {
    const stored = window.localStorage.getItem('bikhabar-news-sound');
    if (stored === '0') soundEnabled = false;
  } catch (_error) {}

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

  function isTerminal(item) {
    return terminalStatuses.has(String(item?.panel_status || ''));
  }

  function isMachineReady(item) {
    const mode = String(item?.translation_mode || '');
    return item?.machine_translation_status === 'passed' || mode === 'machine_persian' || mode === 'source_persian';
  }

  function storyTimeOf(item) {
    return String(item?.story_time || item?.published_at_source || item?.updated_at || '');
  }

  function machinePublishButton(actions) {
    return Array.from(actions?.querySelectorAll('[data-v4-action]') || [])
      .find(node => node.dataset.v4Action === 'publish-machine') || null;
  }

  function ensureMachinePublishButton(card, ready) {
    const actions = card?.querySelector('.v41-story-actions');
    if (!actions) return;
    const existing = machinePublishButton(actions);
    if (!ready) {
      existing?.remove();
      card.dataset.machineReady = '0';
      return;
    }
    card.dataset.machineReady = '1';
    if (existing) return;
    const button = actionButton('انتشار مستقیم', 'publish-machine', 'primary');
    const before = actions.querySelector('[data-v4-action="translate-luna"]');
    actions.insertBefore(button, before || actions.firstChild);
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
    const machineReady = card.dataset.machineReady === '1';
    actions.replaceChildren();
    if (machineReady) actions.appendChild(actionButton('انتشار مستقیم', 'publish-machine', 'primary'));
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

  function updateSoundButton() {
    if (!soundButton) return;
    soundButton.textContent = soundEnabled ? 'صدای خبر: روشن' : 'صدای خبر: خاموش';
    soundButton.setAttribute('aria-pressed', soundEnabled ? 'true' : 'false');
  }

  function playNewStoryAlarm() {
    if (!soundEnabled) return;
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

  function unlockNewsroomAudio({playPending = true} = {}) {
    if (!soundEnabled) return Promise.resolve(false);
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return Promise.resolve(false);
    audioContext = audioContext || new AudioContextClass();
    return Promise.resolve(audioContext.resume()).then(() => {
      audioUnlocked = true;
      let pending = false;
      try { pending = window.sessionStorage.getItem('bikhabar-pending-news-alarm') === '1'; } catch (_error) {}
      if (pending && playPending) playNewStoryAlarm();
      return true;
    }).catch(() => false);
  }

  function newStoryIds(items) {
    const fresh = [];
    items.forEach(item => {
      const id = String(item.id || item.item_id || '');
      if (!id || isTerminal(item) || !isMachineReady(item)) return;
      if (!knownStoryIds.has(id)) fresh.push(id);
      knownStoryIds.add(id);
    });
    return fresh;
  }

  function cardForId(id) {
    return Array.from(feed.querySelectorAll('[data-story-id]'))
      .find(node => String(node.dataset.storyId || '') === String(id || '')) || null;
  }

  function removeTerminalCards(items) {
    items.forEach(item => {
      if (!isTerminal(item)) return;
      cardForId(item.id || item.item_id)?.remove();
    });
  }

  function makeMeta(item) {
    const meta = document.createElement('div');
    meta.className = 'v4-story-meta';
    const source = document.createElement('span');
    source.className = 'v4-source-badge';
    source.textContent = item.source || 'منبع خبری';
    meta.appendChild(source);

    const storyTime = storyTimeOf(item);
    if (storyTime) {
      const time = document.createElement('time');
      time.dateTime = storyTime;
      time.dataset.v4RelativeTime = storyTime;
      time.dataset.v4Exact = '1';
      time.textContent = V4.storyTime(storyTime);
      time.title = V4.exactTime(storyTime);
      meta.appendChild(time);
    }

    const state = document.createElement('span');
    state.className = 'v4-state-badge';
    state.textContent = item.panel_status_fa || item.panel_status || 'تازه';
    meta.appendChild(state);
    return meta;
  }

  function createStoryCard(item) {
    const id = String(item.id || item.item_id || '');
    const card = document.createElement('article');
    card.className = 'v4-story-card v41-story-card';
    card.dataset.v4StoryCard = '1';
    card.dataset.storyId = id;
    card.dataset.machineReady = isMachineReady(item) ? '1' : '0';
    card.dataset.finalReady = '0';
    card.appendChild(makeMeta(item));

    const original = document.createElement('div');
    original.className = 'v4-original v41-original';
    const machineLabel = document.createElement('div');
    machineLabel.className = 'v41-translation-label';
    const labelText = document.createElement('span');
    labelText.textContent = 'ترجمه ماشینی';
    const labelState = document.createElement('small');
    labelState.textContent = isMachineReady(item) ? 'آماده بررسی تو' : 'در حال آماده‌سازی';
    machineLabel.append(labelText, labelState);
    const title = document.createElement('h3');
    title.dataset.v41PublishTitle = '1';
    title.textContent = item.title || 'ترجمه ماشینی در حال آماده‌سازی';
    original.append(machineLabel, title);
    if (item.body) {
      const body = document.createElement('p');
      body.dataset.v41PublishBody = '1';
      body.textContent = item.body;
      original.appendChild(body);
    }
    card.appendChild(original);

    const luna = document.createElement('div');
    luna.className = 'v4-luna v41-translation';
    luna.dataset.v41Translation = '1';
    const lunaLabel = document.createElement('div');
    lunaLabel.className = 'v41-translation-label';
    const lunaLabelText = document.createElement('span');
    lunaLabelText.textContent = 'نسخه Luna';
    const lunaState = document.createElement('small');
    lunaState.textContent = 'اختیاری';
    lunaLabel.append(lunaLabelText, lunaState);
    const lunaHelp = document.createElement('p');
    lunaHelp.textContent = 'اگر بازنویسی نهایی می‌خواهی، «ترجمه با Luna» را بزن.';
    luna.append(lunaLabel, lunaHelp);
    card.appendChild(luna);

    const actions = document.createElement('div');
    actions.className = 'v4-story-actions v41-story-actions';
    if (isMachineReady(item)) actions.appendChild(actionButton('انتشار مستقیم', 'publish-machine', 'primary'));
    actions.appendChild(actionButton('ترجمه با Luna', 'translate-luna'));
    const publishLuna = actionButton('انتشار نسخه Luna', 'publish-luna', 'primary');
    publishLuna.disabled = true;
    publishLuna.setAttribute('aria-disabled', 'true');
    publishLuna.title = 'ابتدا نسخه Luna را بسازید';
    actions.appendChild(publishLuna);
    actions.appendChild(actionButton('بررسی / ویرایش', 'edit-final'));
    actions.appendChild(actionButton('رد و مسدودکردن', 'reject-block', 'danger'));
    if (item.source_url) {
      const link = document.createElement('a');
      link.className = 'v4-button v4-button-secondary v41-source-link';
      link.href = item.source_url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = 'اصل خبر';
      actions.appendChild(link);
    }
    card.appendChild(actions);

    const status = document.createElement('div');
    status.className = 'v4-story-progress';
    status.dataset.v4StoryProgress = '1';
    status.hidden = true;
    card.appendChild(status);
    return card;
  }

  function patchStoryCard(card, item) {
    if (!card) return;
    const ready = isMachineReady(item);
    ensureMachinePublishButton(card, ready);

    const source = card.querySelector('.v4-source-badge');
    if (source && item.source) source.textContent = item.source;

    const storyTime = storyTimeOf(item);
    let time = card.querySelector('.v4-story-meta time');
    if (storyTime) {
      if (!time) {
        time = document.createElement('time');
        card.querySelector('.v4-story-meta')?.insertBefore(time, card.querySelector('.v4-state-badge'));
      }
      time.dateTime = storyTime;
      time.dataset.v4RelativeTime = storyTime;
      time.dataset.v4Exact = '1';
      time.textContent = V4.storyTime(storyTime);
      time.title = V4.exactTime(storyTime);
    }

    const title = card.querySelector('[data-v41-publish-title]');
    if (title && item.title) title.textContent = item.title;
    let body = card.querySelector('[data-v41-publish-body]');
    if (item.body) {
      if (!body) {
        body = document.createElement('p');
        body.dataset.v41PublishBody = '1';
        card.querySelector('.v41-original')?.appendChild(body);
      }
      body.textContent = item.body;
    } else {
      body?.remove();
    }
    const labelState = card.querySelector('.v41-original .v41-translation-label small');
    if (labelState) labelState.textContent = ready ? 'آماده بررسی تو' : 'در حال آماده‌سازی';
    const state = card.querySelector('.v4-state-badge');
    if (state) state.textContent = item.panel_status_fa || item.panel_status || 'تازه';
  }

  function syncLiveCards(items) {
    const active = items.filter(item => !isTerminal(item));
    if (active.length) feed.querySelector('.v4-empty')?.remove();

    const ordered = document.createDocumentFragment();
    active.forEach(item => {
      const id = String(item.id || item.item_id || '');
      if (!id) return;
      let card = cardForId(id);
      if (!card) card = createStoryCard(item);
      else patchStoryCard(card, item);
      ordered.appendChild(card);
    });
    feed.appendChild(ordered);
    V4.refreshTimeNodes(feed);
  }

  async function localizePending(items) {
    const ids = items
      .filter(item => item.needs_localization && !isTerminal(item))
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

  function setRefreshState(message) {
    if (refreshState) refreshState.textContent = message;
  }

  async function refreshLiveFeed({manual = false} = {}) {
    if (refreshRunning) return;
    refreshRunning = true;
    refreshButton?.setAttribute('disabled', 'disabled');
    if (manual) setRefreshState('در حال دریافت تازه‌ترین خبرها…');

    try {
      const payload = await V4.requestJSON('/api/live-feed');
      const items = Array.isArray(payload.items) ? payload.items : [];
      removeTerminalCards(items);
      const freshIds = newStoryIds(items);
      syncLiveCards(items);

      const localized = await localizePending(items);
      localized.forEach(item => {
        patchStoryCard(cardForId(item.id || item.item_id), item);
        const id = String(item.id || item.item_id || '');
        if (id && !knownStoryIds.has(id) && isMachineReady(item)) freshIds.push(id);
        if (id && isMachineReady(item)) knownStoryIds.add(id);
      });

      if (initialSnapshotComplete && freshIds.length) {
        playNewStoryAlarm();
        V4.toast(`${freshIds.length.toLocaleString('fa-IR')} خبر تازه رسید.`, 'success');
      }
      initialSnapshotComplete = true;
      const now = new Date();
      const clock = new Intl.DateTimeFormat('fa-IR', {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}).format(now);
      setRefreshState(`آخرین بروزرسانی: ${clock} · ${items.length.toLocaleString('fa-IR')} ورودی`);
    } catch (error) {
      setRefreshState('بروزرسانی ناموفق؛ دوباره تلاش می‌شود');
      if (manual) V4.toast(error.message || 'دریافت خبرهای جدید ناموفق بود.', 'error');
    } finally {
      refreshRunning = false;
      refreshButton?.removeAttribute('disabled');
    }
  }

  feed.addEventListener('click', event => {
    const target = event.target.closest('[data-v4-action]');
    if (!target || target.disabled) return;
    event.preventDefault();
    const card = target.closest('[data-story-id]');
    const action = target.dataset.v4Action;
    if (action === 'translate-luna') void translateWithLuna(card);
    if (action === 'edit-final') void moveToReview(card);
    if (action === 'publish-machine') void publishCopy(card, 'machine');
    if (action === 'publish-luna') void publishCopy(card, 'luna');
    if (action === 'reject-block') void rejectAndBlock(card);
  });

  refreshButton?.addEventListener('click', () => void refreshLiveFeed({manual: true}));
  soundButton?.addEventListener('click', () => {
    soundEnabled = !soundEnabled;
    try { window.localStorage.setItem('bikhabar-news-sound', soundEnabled ? '1' : '0'); } catch (_error) {}
    updateSoundButton();
    if (!soundEnabled) {
      try { window.sessionStorage.removeItem('bikhabar-pending-news-alarm'); } catch (_error) {}
      V4.toast('صدای خبر خاموش شد.');
      return;
    }
    void unlockNewsroomAudio({playPending: false}).then(unlocked => {
      if (unlocked) {
        playNewStoryAlarm();
        V4.toast('صدای خبر روشن شد.', 'success');
      } else {
        V4.toast('مرورگر اجازه پخش صدا نداد.', 'error');
      }
    });
  });

  document.addEventListener('pointerdown', () => { void unlockNewsroomAudio(); }, {once: true});
  document.addEventListener('keydown', () => { void unlockNewsroomAudio(); }, {once: true});

  updateSoundButton();
  window.setTimeout(() => void refreshLiveFeed(), 700);
  window.setInterval(() => void refreshLiveFeed(), 5000);
})();