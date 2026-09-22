(() => {
  const title = document.getElementById('finalTitle');
  const body = document.getElementById('finalBody');
  const mode = document.getElementById('copyMode');
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', () => {
      title.value = button.dataset.title || '';
      body.value = button.dataset.body || '';
      mode.value = button.dataset.copy;
    });
  });
  [title, body].filter(Boolean).forEach(field => field.addEventListener('input', () => { mode.value = 'edited'; }));
  document.querySelectorAll('[data-confirm]').forEach(button => {
    button.addEventListener('click', event => {
      if (!window.confirm(button.dataset.confirm)) event.preventDefault();
    });
  });
  const list = document.getElementById('storyList');
  if (list) {
    window.setInterval(async () => {
      if (document.hidden) return;
      const response = await fetch(`${list.dataset.api}${window.location.search}`, {headers: {'Accept': 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      const visible = new Set([...list.querySelectorAll('[data-story-id]')].map(node => node.dataset.storyId));
      if (data.items.some(item => !visible.has(item.id)) || data.items.length !== visible.size) window.location.reload();
    }, 5000);
  }
})();
