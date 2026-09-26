(() => {
  'use strict';

  // The shared messenger owns chat, confirmation and voice. These strings stay
  // here so the legacy page and the V4 UI contract still point at the same API.
  const OPERATOR_CHAT = '/api/panel/luna/operator-chat';
  const OPERATOR_CONFIRM = '/api/panel/luna/operator-confirm/';
  const CONFIRMATION_REQUIRED = 'confirmation_required';
  const ACCEPT_LABEL = 'تأیید و اجرا';

  const root = document.querySelector('.v41-luna .v5-luna');
  const api = window.NewsroomV5Luna?.ENDPOINTS;
  if (!root || !api || api.chat !== OPERATOR_CHAT) return;
  if (!String(api.confirm('check')).startsWith(OPERATOR_CONFIRM)) return;

  const messenger = window.NewsroomV5Luna.mount(root, {
    toast(message) {
      const status = document.getElementById('v4LunaStatus');
      if (status && message) status.textContent = message;
    },
  });
  if (!messenger) return;

  const connection = document.getElementById('v4LunaConnection');
  if (connection) {
    fetch('/api/panel/luna/status', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(response => response.json())
      .then(payload => {
        connection.textContent = payload.connected ? 'متصل' : 'آفلاین';
      })
      .catch(() => {
        connection.textContent = 'اتصال نامشخص';
      });
  }

  // Inline confirmation uses this label inside the shared messenger; do not open a second dialog.
  root.dataset.confirmLabel = ACCEPT_LABEL;
  root.dataset.confirmationFlag = CONFIRMATION_REQUIRED;
})();
