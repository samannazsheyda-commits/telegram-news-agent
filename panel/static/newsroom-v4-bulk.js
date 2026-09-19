(() => {
  const feed = document.getElementById('v4LiveFeed');
  if (!feed || !window.BikhabarV4) return;
  const V4 = window.BikhabarV4;

  const controls = document.createElement('div');
  controls.className = 'v4-toolbar';
  controls.setAttribute('aria-label', 'عملیات گروهی خبرها');

  const selectAll = document.createElement('button');
  selectAll.type = 'button';
  selectAll.className = 'v4-button v4-button-secondary';
  selectAll.textContent = 'انتخاب همه';

  const bulkRemove = document.createElement('button');
  bulkRemove.type = 'button';
  bulkRemove.className = 'v4-button v4-button-danger';
  bulkRemove.textContent = 'رد گروهی';
  bulkRemove.disabled = true;

  controls.append(selectAll, bulkRemove);
  feed.parentElement?.insertBefore(controls, feed);

  function visibleCards() {
    return Array.from(feed.querySelectorAll('[data-story-id]')).filter(card => !card.hidden && card.isConnected);
  }

  function checkboxFor(card) {
    return card.querySelector('[data-v4-bulk-select]');
  }

  function selectedCards() {
    return visibleCards().filter(card => checkboxFor(card)?.checked);
  }

  function updateControls() {
    const cards = visibleCards();
    const selected = selectedCards();
    bulkRemove.disabled = selected.length === 0;
    bulkRemove.textContent = selected.length
      ? `رد گروهی (${selected.length.toLocaleString('fa-IR')})`
      : 'رد گروهی';
    selectAll.textContent = cards.length > 0 && selected.length === cards.length ? 'لغو انتخاب همه' : 'انتخاب همه';
  }

  function ensureCheckbox(card) {
    if (!(card instanceof Element) || checkboxFor(card)) return;
    const meta = card.querySelector('.v4-story-meta');
    if (!meta) return;
    const label = document.createElement('label');
    label.className = 'v4-source-badge';
    label.style.cursor = 'pointer';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.dataset.v4BulkSelect = '1';
    checkbox.setAttribute('aria-label', 'انتخاب خبر برای عملیات گروهی');
    checkbox.style.marginInlineEnd = '6px';
    const text = document.createElement('span');
    text.textContent = 'انتخاب';
    label.append(checkbox, text);
    meta.prepend(label);
  }

  function scan(root = feed) {
    if (root.matches?.('[data-story-id]')) ensureCheckbox(root);
    root.querySelectorAll?.('[data-story-id]').forEach(ensureCheckbox);
    updateControls();
  }

  selectAll.addEventListener('click', () => {
    const cards = visibleCards();
    const shouldSelect = !cards.length ? false : selectedCards().length !== cards.length;
    cards.forEach(card => {
      const checkbox = checkboxFor(card);
      if (checkbox) checkbox.checked = shouldSelect;
    });
    updateControls();
  });

  feed.addEventListener('change', event => {
    if (event.target.matches?.('[data-v4-bulk-select]')) updateControls();
  });

  bulkRemove.addEventListener('click', async () => {
    const cards = selectedCards();
    if (!cards.length) return;
    const count = cards.length;
    const accepted = await V4.confirmAction({
      title: `${count.toLocaleString('fa-IR')} خبر رد و مسدود شود؟`,
      text: 'خبرهای انتخاب‌شده از داشبورد فعال حذف و Block می‌شوند تا دوباره وارد چرخه انتشار نشوند.',
      accept: 'تأیید رد گروهی',
    });
    if (!accepted) return;

    selectAll.disabled = true;
    bulkRemove.disabled = true;
    let removed = 0;
    let failed = 0;
    for (const card of cards) {
      const id = String(card.dataset.storyId || '');
      if (!id) continue;
      try {
        await V4.requestJSON(`/api/panel/luna/block-story/${encodeURIComponent(id)}`, {method: 'POST'});
        card.remove();
        removed += 1;
      } catch (_error) {
        failed += 1;
        const checkbox = checkboxFor(card);
        if (checkbox) checkbox.checked = false;
      }
    }
    selectAll.disabled = false;
    updateControls();
    if (removed) V4.toast(`${removed.toLocaleString('fa-IR')} خبر از صف فعال حذف و مسدود شد.`, 'success');
    if (failed) V4.toast(`حذف ${failed.toLocaleString('fa-IR')} خبر ناموفق بود.`, 'error');
  });

  scan();
  const observer = new MutationObserver(() => scan());
  observer.observe(feed, {childList: true, subtree: true, attributes: true, attributeFilter: ['hidden']});
})();