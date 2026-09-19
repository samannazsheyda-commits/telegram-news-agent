(() => {
  const feed = document.getElementById('v4LiveFeed');
  if (!feed || !window.BikhabarV4) return;
  const V4 = window.BikhabarV4;

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

  function renderTranslation(card, result) {
    const panel = card?.querySelector('[data-v41-translation]');
    const actions = card?.querySelector('.v41-story-actions');
    if (!panel || !actions || !result?.quality_passed) return;
    panel.replaceChildren();

    const label = document.createElement('div');
    label.className = 'v41-translation-label';
    const labelMain = document.createElement('span');
    labelMain.textContent = 'ترجمه Luna';
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

    const translate = document.createElement('button');
    translate.className = 'v4-button v4-button-secondary';
    translate.type = 'button';
    translate.dataset.v4Action = 'translate-luna';
    translate.textContent = 'ترجمه دوباره';
    actions.appendChild(translate);

    const edit = document.createElement('button');
    edit.className = 'v4-button v4-button-secondary';
    edit.type = 'button';
    edit.dataset.v4Action = 'edit-final';
    edit.textContent = 'بررسی / ویرایش';
    actions.appendChild(edit);

    const publish = document.createElement('button');
    publish.className = 'v4-button v4-button-primary';
    publish.type = 'button';
    publish.dataset.v4Action = 'publish-final';
    publish.textContent = 'انتشار';
    actions.appendChild(publish);

    const reject = document.createElement('button');
    reject.className = 'v4-button v4-button-danger';
    reject.type = 'button';
    reject.dataset.v4Action = 'reject-block';
    reject.textContent = 'رد و مسدودکردن';
    actions.appendChild(reject);
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
      V4.toast('ترجمه Luna آماده است.', 'success');
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

  async function publishFinal(card) {
    const id = card?.dataset.storyId;
    if (!id || card.dataset.finalReady !== '1' || card.classList.contains('is-busy')) return;
    const title = card.querySelector('[data-v41-title]')?.textContent?.trim() || '';
    const body = card.querySelector('[data-v41-body]')?.textContent?.trim() || '';
    const preview = [title, body].filter(Boolean).join('\n\n');
    const accepted = await V4.confirmAction({
      title: 'همین نسخه منتشر شود؟',
      text: preview.length > 700 ? `${preview.slice(0, 700)}…` : preview,
      accept: 'انتشار',
    });
    if (!accepted) return;
    card.classList.add('is-busy');
    progress(card, 'نسخه تأییدشده در صف امن V3 قرار می‌گیرد…');
    try {
      const queued = await V4.requestJSON(`/api/panel/luna/publish-final/${encodeURIComponent(id)}`, {method: 'POST'});
      const done = await poll(queued.command_id, card);
      progress(card, done.telegram_message_id ? `منتشر شد · Message ID ${done.telegram_message_id}` : 'منتشر شد', 'success');
      V4.toast('خبر منتشر شد.', 'success');
    } catch (error) {
      progress(card, error.message, 'error');
      V4.toast(error.message, 'error');
    } finally {
      card.classList.remove('is-busy');
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

  feed.addEventListener('click', event => {
    const target = event.target.closest('[data-v4-action]');
    if (!target) return;
    event.preventDefault();
    const card = target.closest('[data-story-id]');
    const action = target.dataset.v4Action;
    if (action === 'translate-luna') void translateWithLuna(card);
    if (action === 'edit-final') void moveToReview(card);
    if (action === 'publish-final') void publishFinal(card);
    if (action === 'reject-block') void rejectAndBlock(card);
  });
})();
