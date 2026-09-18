(() => {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  function headers(extra = {}) {
    const token = csrfToken();
    return token ? {...extra, 'X-CSRFToken': token} : {...extra};
  }

  async function requestJSON(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      cache: 'no-store',
      ...options,
      headers: headers(options.headers || {}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      const error = new Error(payload.message || payload.error || `HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function toast(message, kind = '') {
    const stack = document.getElementById('v4ToastStack');
    if (!stack || !message) return;
    const item = document.createElement('div');
    item.className = `v4-toast ${kind}`.trim();
    item.textContent = message;
    stack.appendChild(item);
    window.setTimeout(() => item.remove(), 4200);
  }

  function confirmAction({title = 'تأیید عملیات', text = 'از انجام این عملیات مطمئنی؟', accept = 'تأیید'} = {}) {
    const dialog = document.getElementById('v4ConfirmDialog');
    if (!dialog || typeof dialog.showModal !== 'function') {
      return Promise.resolve(window.confirm(text));
    }
    document.getElementById('v4ConfirmTitle').textContent = title;
    document.getElementById('v4ConfirmText').textContent = text;
    document.getElementById('v4ConfirmAccept').textContent = accept;
    dialog.showModal();
    return new Promise(resolve => {
      const done = () => {
        dialog.removeEventListener('close', done);
        resolve(dialog.returnValue === 'confirm');
      };
      dialog.addEventListener('close', done, {once: true});
    });
  }

  function relativeTime(value) {
    if (!value) return '—';
    const stamp = Date.parse(value);
    if (!Number.isFinite(stamp)) return value;
    const seconds = Math.max(0, Math.floor((Date.now() - stamp) / 1000));
    if (seconds < 60) return 'همین الان';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes.toLocaleString('fa-IR')} دقیقه قبل`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours.toLocaleString('fa-IR')} ساعت قبل`;
    const days = Math.floor(hours / 24);
    return `${days.toLocaleString('fa-IR')} روز قبل`;
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-v4-confirm]');
    if (!button) return;
    event.preventDefault();
    void confirmAction({
      title: button.dataset.v4ConfirmTitle || 'تأیید عملیات',
      text: button.dataset.v4Confirm || 'از انجام این عملیات مطمئنی؟',
      accept: button.dataset.v4ConfirmAccept || 'تأیید',
    }).then(ok => {
      if (!ok) return;
      const formId = button.dataset.v4SubmitForm;
      if (formId) document.getElementById(formId)?.requestSubmit();
    });
  });

  document.querySelectorAll('[data-v4-relative-time]').forEach(node => {
    node.textContent = relativeTime(node.getAttribute('datetime') || node.dataset.v4RelativeTime);
  });

  window.BikhabarV4 = {requestJSON, toast, confirmAction, relativeTime, headers};
})();
