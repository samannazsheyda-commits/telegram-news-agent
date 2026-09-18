(() => {
  const sheet = document.getElementById('editorSheet');
  const feed = document.getElementById('liveFeed');
  if (!sheet || !feed) return;

  const UI = window.BikhabarUI || {};
  const storyIdInput = document.getElementById('editorStoryId');
  const titleInput = document.getElementById('editorTitle');
  const bodyInput = document.getElementById('editorBody');
  const sourceNode = document.getElementById('editorSource');
  const sourceLink = document.getElementById('editorSourceLink');
  const applyButton = document.getElementById('editorApply');
  let activeId = '';

  function closeEditor() {
    sheet.hidden = true;
    document.body.style.overflow = '';
    activeId = '';
  }

  function openEditor(card) {
    const id = String(card?.dataset.storyId || '').trim();
    const api = window.BikhabarV4;
    const luna = api?.getLuna(id);
    const story = api?.story(id);
    if (!id || !luna) {
      UI.toast?.('اول نسخه لونا را آماده کن.', 'error');
      return;
    }
    activeId = id;
    storyIdInput.value = id;
    titleInput.value = String(luna.title || '');
    bodyInput.value = String(luna.body || '');
    sourceNode.textContent = String(story?.source || 'منبع');
    const url = String(story?.source_url || '').trim();
    sourceLink.href = url || '#';
    sourceLink.hidden = !url;
    sheet.hidden = false;
    document.body.style.overflow = 'hidden';
    window.setTimeout(() => titleInput.focus(), 0);
  }

  function copy() {
    const title = titleInput.value.trim();
    const body = bodyInput.value.trim();
    if (!title) throw new Error('تیتر نهایی نمی‌تواند خالی باشد.');
    if (title.length > 280 || body.length > 4000) throw new Error('متن از حد مجاز طولانی‌تر است.');
    return {title, body};
  }

  feed.addEventListener('click', event => {
    const button = event.target.closest('[data-action="edit-luna"]');
    if (!button) return;
    event.preventDefault();
    openEditor(button.closest('[data-story-id]'));
  });

  sheet.querySelectorAll('[data-editor-close]').forEach(node => node.addEventListener('click', closeEditor));
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !sheet.hidden) closeEditor();
  });

  applyButton?.addEventListener('click', () => {
    try {
      const value = copy();
      if (!activeId) throw new Error('شناسه خبر معتبر نیست.');
      window.BikhabarV4?.setLuna(activeId, value.title, value.body);
      UI.toast?.('ویرایش نسخه لونا اعمال شد؛ هنوز منتشر نشده.', 'success');
      closeEditor();
    } catch (error) {
      UI.toast?.(error.message, 'error');
    }
  });
})();
