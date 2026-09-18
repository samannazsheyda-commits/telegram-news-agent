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

  async function sendToLuna(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    card.classList.add('is-busy');
    progress(card, 'Luna در حال بررسی و ساخت نسخه نهایی…');
    try {
      const result = await V4.requestJSON(`/api/panel/luna/preview/${encodeURIComponent(id)}`, {method: 'POST'});
      progress(card, 'نسخه Luna آماده شد', 'success');
      V4.toast(result.preview?.decision === 'REJECT' ? 'Luna این خبر را برای انتشار مناسب ندانست.' : 'نسخه نهایی Luna آماده بررسی است.', 'success');
      window.setTimeout(() => window.location.reload(), 350);
    } catch (error) {
      progress(card, error.message, 'error');
      V4.toast(error.message, 'error');
    } finally {
      card.classList.remove('is-busy');
    }
  }

  async function loadMachinePreview(card) {
    const id = card?.dataset.storyId;
    const machine = card?.querySelector('.v4-machine p');
    if (!id || !machine || machine.dataset.loaded === '1' || card.dataset.machineBusy === '1') return;
    if (!machine.textContent.includes('هنوز آماده نیست')) return;
    card.dataset.machineBusy = '1';
    try {
      const result = await V4.requestJSON(`/api/panel/machine-preview/${encodeURIComponent(id)}`, {method: 'POST'});
      machine.textContent = result.preview || 'ترجمه ماشینی موقتاً در دسترس نیست';
      machine.dataset.loaded = '1';
    } catch (error) {
      machine.textContent = error.message || 'ترجمه ماشینی موقتاً در دسترس نیست';
    } finally {
      delete card.dataset.machineBusy;
    }
  }

  async function publishFinal(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    const accepted = await V4.confirmAction({
      title: 'نسخه نهایی Luna منتشر شود؟',
      text: 'همین نسخه‌ای که دیدی برای انتشار در تلگرام ارسال می‌شود.',
      accept: 'انتشار',
    });
    if (!accepted) return;
    card.classList.add('is-busy');
    progress(card, 'در حال قراردادن نسخه تأییدشده در صف انتشار…');
    try {
      const queued = await V4.requestJSON(`/api/panel/luna/publish/${encodeURIComponent(id)}`, {method: 'POST'});
      const done = await poll(queued.command_id, card);
      progress(card, done.telegram_message_id ? `منتشر شد · Message ID ${done.telegram_message_id}` : 'منتشر شد', 'success');
      V4.toast('نسخه تأییدشده Luna منتشر شد.', 'success');
    } catch (error) {
      progress(card, error.message, 'error');
      V4.toast(error.message, 'error');
    } finally {
      card.classList.remove('is-busy');
    }
  }

  async function reject(card) {
    const id = card?.dataset.storyId;
    if (!id || card.classList.contains('is-busy')) return;
    const accepted = await V4.confirmAction({title: 'این خبر رد شود؟', text: 'خبر از صف تصمیم‌گیری پنل خارج می‌شود.', accept: 'رد خبر'});
    if (!accepted) return;
    card.classList.add('is-busy');
    try {
      await V4.requestJSON(`/api/newsroom/live/${encodeURIComponent(id)}/reject`, {method: 'POST'});
      card.remove();
      V4.toast('خبر رد شد.', 'success');
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
    if (action === 'send-luna') void sendToLuna(card);
    if (action === 'publish-final') void publishFinal(card);
    if (action === 'reject') void reject(card);
    if (action === 'edit-final' && card?.dataset.storyId) window.location.href = `/review/${encodeURIComponent(card.dataset.storyId)}`;
  });

  const observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      void loadMachinePreview(entry.target);
    });
  }, {rootMargin: '180px 0px'}) : null;

  feed.querySelectorAll('[data-v4-story-card="1"]').forEach(card => {
    if (observer) observer.observe(card);
    else void loadMachinePreview(card);
  });
})();
