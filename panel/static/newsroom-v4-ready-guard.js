(() => {
  const feed = document.getElementById('v4LiveFeed');
  if (!feed) return;

  function ensureLunaPublishState(card) {
    if (!(card instanceof Element)) return;
    const actions = card.querySelector('.v41-story-actions');
    if (!actions) return;

    const ready = card.dataset.finalReady === '1';
    let button = actions.querySelector('[data-v4-action="publish-luna"]');

    if (!button) {
      button = document.createElement('button');
      button.className = 'v4-button v4-button-primary';
      button.type = 'button';
      button.dataset.v4Action = 'publish-luna';
      button.textContent = 'انتشار نسخه Luna';
      const edit = actions.querySelector('[data-v4-action="edit-final"]');
      actions.insertBefore(button, edit || null);
    }

    button.disabled = !ready;
    button.setAttribute('aria-disabled', ready ? 'false' : 'true');
    if (ready) {
      button.removeAttribute('title');
    } else {
      button.title = 'ابتدا نسخه Luna را بسازید';
    }
  }

  function scan(root = feed) {
    if (root.matches?.('[data-v4-story-card]')) ensureLunaPublishState(root);
    root.querySelectorAll?.('[data-v4-story-card]').forEach(ensureLunaPublishState);
  }

  scan();
  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach(node => {
        if (node instanceof Element) scan(node);
      });
    }
  });
  observer.observe(feed, {childList: true, subtree: true});
})();
