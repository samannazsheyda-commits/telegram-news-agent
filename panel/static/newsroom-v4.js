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
      throw new Error(data.message || data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  function confirmAction({ title = 'تأیید عملیات', message = 'از انجام این کار مطمئنی؟' } = {}) {
    return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  }

  function openLuna() {
    const panel = document.getElementById('v4LunaAssistant');
    const launcher = document.getElementById('v4LunaLauncher');
    if (!panel) return;
    panel.classList.add('is-open');
    panel.setAttribute('aria-hidden', 'false');
    launcher?.setAttribute('aria-expanded', 'true');
    window.setTimeout(() => document.getElementById('v4LunaInput')?.focus(), 40);
  }

  function closeLuna() {
    const panel = document.getElementById('v4LunaAssistant');
    const launcher = document.getElementById('v4LunaLauncher');
    if (!panel) return;
    panel.classList.remove('is-open');
    panel.setAttribute('aria-hidden', 'true');
    launcher?.setAttribute('aria-expanded', 'false');
  }

  function appendLunaMessage(text, who = 'luna') {
    const thread = document.getElementById('v4LunaThread');
    if (!thread || !text) return;
    const node = document.createElement('div');
    node.className = `v4-luna-message ${who === 'user' ? 'is-user' : 'is-luna'}`;
    node.textContent = String(text);
    thread.appendChild(node);
    thread.scrollTop = thread.scrollHeight;
  }

  async function sendLunaMessage(message) {
    const text = String(message || '').trim();
    if (!text) return;
    const input = document.getElementById('v4LunaInput');
    const button = document.getElementById('v4LunaSend');
    appendLunaMessage(text, 'user');
    if (input) input.value = '';
    if (button) {
      button.disabled = true;
      button.textContent = 'Luna…';
    }
    try {
      const result = await postJSON('/api/v4/assistant/message', {message: text});
      appendLunaMessage(result.reply_fa || result.message || 'انجام شد.', 'luna');
      if (result.intent === 'update_daily_quota') {
        window.dispatchEvent(new CustomEvent('newsroom:v4-settings-changed'));
      }
    } catch (error) {
      appendLunaMessage(error.message || 'Luna فعلاً پاسخ نداد.', 'luna');
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = 'ارسال';
      }
    }
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
    if (event.target.id === 'v4MoreSheet') {
      closeMoreSheet();
      return;
    }
    if (event.target.closest('#v4LunaLauncher')) {
      openLuna();
      return;
    }
    if (event.target.closest('#v4LunaClose')) {
      closeLuna();
      return;
    }
    const chip = event.target.closest('[data-luna-prompt]');
    if (chip) {
      openLuna();
      sendLunaMessage(chip.dataset.lunaPrompt || '');
    }
  });

  document.addEventListener('submit', (event) => {
    if (event.target.id !== 'v4LunaForm') return;
    event.preventDefault();
    sendLunaMessage(document.getElementById('v4LunaInput')?.value || '');
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMoreSheet();
      closeLuna();
    }
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && document.activeElement?.id === 'v4LunaInput') {
      event.preventDefault();
      sendLunaMessage(document.getElementById('v4LunaInput')?.value || '');
    }
  });

  window.NewsroomV4 = {
    csrfToken,
    toast,
    postJSON,
    confirmAction,
    openMoreSheet,
    closeMoreSheet,
    openLuna,
    closeLuna,
    sendLunaMessage,
  };
})();
