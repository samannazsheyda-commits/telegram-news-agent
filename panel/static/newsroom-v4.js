(() => {
  'use strict';

  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  function toast(message, kind = 'info', timeout = 3500) {
    const stack = document.getElementById('v4ToastStack');
    if (!stack || !message) return;
    const node = document.createElement('div');
    node.className = `v4-toast${kind === 'error' ? ' is-error' : ''}`;
    node.textContent = String(message);
    stack.appendChild(node);
    window.setTimeout(() => node.remove(), timeout);
  }

  function closeMoreSheet() {
    const sheet = document.getElementById('v4MoreSheet');
    if (!sheet) return;
    sheet.classList.remove('is-open');
    sheet.setAttribute('aria-hidden', 'true');
  }

  function openMoreSheet() {
    const sheet = document.getElementById('v4MoreSheet');
    if (!sheet) return;
    sheet.classList.add('is-open');
    sheet.setAttribute('aria-hidden', 'false');
  }

  async function postJSON(url, payload = {}) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || data.message || `HTTP ${response.status}`);
    }
    return data;
  }

  function confirmAction({ title = 'تأیید عملیات', message = 'از انجام این کار مطمئنی؟' } = {}) {
    return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  }

  document.addEventListener('click', (event) => {
    const open = event.target.closest('[data-v4-more-open]');
    if (open) {
      event.preventDefault();
      openMoreSheet();
      return;
    }
    const close = event.target.closest('[data-v4-more-close]');
    if (close) {
      event.preventDefault();
      closeMoreSheet();
      return;
    }
    if (event.target.id === 'v4MoreSheet') closeMoreSheet();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMoreSheet();
  });

  window.NewsroomV4 = {
    csrfToken,
    toast,
    postJSON,
    confirmAction,
    openMoreSheet,
    closeMoreSheet,
  };
})();
