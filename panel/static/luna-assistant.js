(() => {
  const form = document.getElementById('v4AssistantForm');
  const input = document.getElementById('v4AssistantInput');
  const log = document.getElementById('v4AssistantLog');
  if (!form || !input || !log || !window.BikhabarV4) return;
  const V4 = window.BikhabarV4;

  function message(text, role = 'luna') {
    const node = document.createElement('div');
    node.className = `v4-chat-msg ${role}`;
    node.textContent = text;
    log.appendChild(node);
    log.scrollTop = log.scrollHeight;
    return node;
  }

  async function ask(text) {
    const clean = String(text || '').trim();
    if (!clean) return;
    message(clean, 'user');
    input.value = '';
    input.disabled = true;
    const pending = message('در حال بررسی…', 'luna');
    try {
      const result = await V4.requestJSON('/api/panel/luna/assistant', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: clean}),
      });
      pending.textContent = result.reply_fa || 'انجام شد.';
      if (result.confirmation_required && result.action_id) {
        const accepted = await V4.confirmAction({
          title: 'Luna این تغییر را انجام دهد؟',
          text: result.reply_fa || 'این اکشن نیاز به تأیید دارد.',
          accept: 'تأیید و اجرا',
        });
        if (!accepted) {
          message('تغییر اجرا نشد.', 'luna');
          return;
        }
        const confirmed = await V4.requestJSON(`/api/panel/luna/assistant/confirm/${encodeURIComponent(result.action_id)}`, {method: 'POST'});
        message(confirmed.reply_fa || 'تغییر انجام شد.', 'luna');
        V4.toast('اکشن Luna با تأیید تو انجام شد.', 'success');
      }
    } catch (error) {
      pending.textContent = error.message || 'Luna فعلاً نتوانست پاسخ بدهد.';
      V4.toast(pending.textContent, 'error');
    } finally {
      input.disabled = false;
      input.focus();
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    void ask(input.value);
  });

  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.addEventListener('click', event => {
    const example = event.target.closest('[data-v4-assistant-example]');
    if (!example) return;
    void ask(example.dataset.v4AssistantExample);
  });
})();
