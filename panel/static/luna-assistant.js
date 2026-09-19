(() => {
  const form = document.getElementById('v4LunaComposer');
  const input = document.getElementById('v4LunaInput');
  const messages = document.getElementById('v4LunaMessages');
  const imageInput = document.getElementById('v4LunaImage');
  const audioInput = document.getElementById('v4LunaAudio');
  const imagePreview = document.getElementById('v4LunaAttachmentPreview');
  const mic = document.getElementById('v4LunaMic');
  const send = document.getElementById('v4LunaSend');
  const connection = document.getElementById('v4LunaConnection');
  const usageBadge = document.getElementById('v4LunaUsage');
  const status = document.getElementById('v4LunaStatus');
  if (!form || !input || !messages || !imageInput || !mic || !send || !window.BikhabarV4) return;

  const V4 = window.BikhabarV4;
  let selectedImage = null;
  let recorder = null;
  let recordingStream = null;
  let audioChunks = [];
  let busy = false;

  function scrollToBottom() { messages.scrollTop = messages.scrollHeight; }

  function message(text, role = 'luna') {
    const article = document.createElement('article');
    article.className = `v41-msg v41-msg-${role}`;
    if (role === 'luna') {
      const avatar = document.createElement('div');
      avatar.className = 'v41-msg-avatar';
      avatar.textContent = 'L';
      article.appendChild(avatar);
    }
    const body = document.createElement('div');
    body.className = 'v41-msg-body';
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    body.appendChild(paragraph);
    article.appendChild(body);
    messages.appendChild(article);
    scrollToBottom();
    return paragraph;
  }

  function toolCard(title, detail = '', kind = '') {
    const node = document.createElement('div');
    node.className = `v41-tool-card ${kind ? `is-${kind}` : ''}`.trim();
    const strong = document.createElement('strong');
    strong.textContent = title;
    node.appendChild(strong);
    if (detail) node.appendChild(document.createTextNode(` · ${detail}`));
    messages.appendChild(node);
    scrollToBottom();
    return node;
  }

  function builderCard(result) {
    const pr = result?.pull_request || {};
    const files = Array.isArray(result?.changed_files) ? result.changed_files : [];
    const node = document.createElement('div');
    node.className = 'v41-tool-card is-success v41-builder-card';
    const title = document.createElement('strong');
    title.textContent = pr.number ? `Builder · PR #${pr.number}` : 'Builder · تغییر آماده شد';
    node.appendChild(title);
    if (result?.summary_fa) {
      const summary = document.createElement('p');
      summary.textContent = result.summary_fa;
      node.appendChild(summary);
    }
    if (files.length) {
      const meta = document.createElement('small');
      meta.textContent = `${files.length.toLocaleString('fa-IR')} فایل تغییر کرد · ${result.branch || ''}`;
      node.appendChild(meta);
    }
    if (pr.url) {
      const link = document.createElement('a');
      link.href = pr.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = 'باز کردن Draft PR';
      node.appendChild(link);
    }
    messages.appendChild(node);
    scrollToBottom();
  }

  function typing() {
    const article = document.createElement('article');
    article.className = 'v41-msg v41-msg-luna';
    const avatar = document.createElement('div');
    avatar.className = 'v41-msg-avatar';
    avatar.textContent = 'L';
    const body = document.createElement('div');
    body.className = 'v41-msg-body';
    body.innerHTML = '<span class="v41-typing" aria-label="Luna در حال پاسخ است"><i></i><i></i><i></i></span>';
    article.append(avatar, body);
    messages.appendChild(article);
    scrollToBottom();
    return {article, body};
  }

  async function revealText(paragraph, text) {
    const resolved = String(text || '');
    if (!resolved) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || resolved.length < 90) {
      paragraph.textContent = resolved;
      return;
    }
    paragraph.textContent = '';
    const chunks = resolved.match(/.{1,18}(?:\s|$)/g) || [resolved];
    for (const chunk of chunks) {
      paragraph.textContent += chunk;
      scrollToBottom();
      await new Promise(resolve => window.setTimeout(resolve, 14));
    }
  }

  function setBusy(value) {
    busy = Boolean(value);
    send.disabled = busy;
    imageInput.disabled = busy;
    if (audioInput) audioInput.disabled = busy;
    if (!recorder || recorder.state === 'inactive') mic.disabled = busy;
  }

  function autoGrow() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(160, Math.max(44, input.scrollHeight))}px`;
  }

  function clearImage() {
    selectedImage = null;
    imageInput.value = '';
    imagePreview.hidden = true;
    imagePreview.replaceChildren();
  }

  function previewImage(file) {
    selectedImage = file;
    const url = URL.createObjectURL(file);
    imagePreview.replaceChildren();
    const label = document.createElement('span');
    label.textContent = file.name || 'تصویر پیوست شد';
    const img = document.createElement('img');
    img.src = url;
    img.alt = 'پیش‌نمایش تصویر';
    img.onload = () => URL.revokeObjectURL(url);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'v41-icon-button';
    remove.style.cssText = 'float:left;width:32px;min-width:32px;height:32px;margin-inline-start:8px';
    remove.textContent = '×';
    remove.setAttribute('aria-label', 'حذف تصویر');
    remove.addEventListener('click', clearImage, {once: true});
    imagePreview.append(remove, label, img);
    imagePreview.hidden = false;
  }

  async function loadStatus() {
    try {
      const info = await V4.requestJSON('/api/panel/luna/usage');
      if (connection) {
        connection.textContent = info.connected ? 'Luna متصل' : 'Luna متصل نیست';
        connection.dataset.connected = info.connected ? '1' : '0';
      }
      if (status) {
        const builder = info.builder_connected ? 'Builder آماده' : 'Builder بدون اتصال GitHub';
        status.textContent = info.connected ? `دستیار هوشمند اتاق خبر · ${builder}` : 'کلید OpenAI روی سرور تنظیم نشده';
      }
      if (usageBadge) {
        const today = info.usage?.today || {};
        const requests = Number(today.requests || 0).toLocaleString('fa-IR');
        const cost = Number(today.estimated_usd || 0);
        usageBadge.textContent = `امروز ${requests} درخواست · $${cost.toFixed(cost < 1 ? 3 : 2)}`;
      }
    } catch (_) {
      if (connection) connection.textContent = 'وضعیت نامشخص';
      if (usageBadge) usageBadge.textContent = 'مصرف امروز: —';
    }
  }

  function showToolEvents(result) {
    for (const event of result.tool_events || []) {
      const label = event.tool || 'ابزار Luna';
      const detail = event.message || (event.confirmation_required ? 'منتظر تأیید تو' : 'انجام شد');
      toolCard(label, detail, event.ok ? 'success' : (event.confirmation_required ? 'warning' : ''));
    }
  }

  async function confirmResult(result) {
    if (!result.confirmation_required || !result.action_id) return;
    const accepted = await V4.confirmAction({
      title: result.mode === 'builder' ? 'Luna وارد حالت Builder شود؟' : 'Luna این کار را انجام دهد؟',
      text: result.summary_fa || result.reply_fa || 'این عملیات نیاز به تأیید دارد.',
      accept: 'تأیید و اجرا',
    });
    if (!accepted) {
      toolCard('عملیات لغو شد', 'هیچ تغییری انجام نشد', 'warning');
      return;
    }
    try {
      const confirmed = await V4.requestJSON(`/api/panel/luna/operator-confirm/${encodeURIComponent(result.action_id)}`, {method: 'POST'});
      if (result.mode === 'builder' && confirmed.pull_request) builderCard(confirmed);
      else toolCard('انجام شد', confirmed.message || confirmed.reply_fa || 'عملیات با تأیید تو اجرا شد.', 'success');
      void loadStatus();
    } catch (error) {
      toolCard('اجرا نشد', error.message || 'این عملیات فعلاً قابل اجرا نیست.', 'warning');
    }
  }

  async function ask() {
    const text = String(input.value || '').trim();
    if ((!text && !selectedImage) || busy) return;

    message(text || 'این تصویر رو بررسی کن', 'user');
    const image = selectedImage;
    input.value = '';
    autoGrow();
    clearImage();
    setBusy(true);
    const pending = typing();

    try {
      const data = new FormData();
      data.append('message', text);
      if (image) data.append('image', image, image.name || 'image.jpg');
      const result = await V4.requestJSON('/api/panel/luna/operator-chat', {method: 'POST', body: data});
      pending.body.replaceChildren();
      const paragraph = document.createElement('p');
      pending.body.appendChild(paragraph);
      await revealText(paragraph, result.reply_fa || 'انجام شد.');
      showToolEvents(result);
      if (result.mode === 'builder') toolCard('Builder', 'درخواست تغییر کد تشخیص داده شد؛ برای شروع تأیید لازم است', 'warning');
      await confirmResult(result);
    } catch (error) {
      pending.body.replaceChildren();
      const paragraph = document.createElement('p');
      paragraph.textContent = error.message || 'Luna فعلاً نتوانست پاسخ بدهد.';
      pending.body.appendChild(paragraph);
      V4.toast(paragraph.textContent, 'error');
    } finally {
      setBusy(false);
      input.focus();
      scrollToBottom();
    }
  }

  function preferredAudioMime() {
    const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
    return options.find(type => window.MediaRecorder?.isTypeSupported?.(type)) || '';
  }

  async function transcribeAudio(fileOrBlob, filename = 'luna-voice.webm') {
    const originalType = String(fileOrBlob?.type || 'audio/webm');
    const cleanType = originalType.split(';', 1)[0] || 'audio/webm';
    const payload = fileOrBlob instanceof File
      ? fileOrBlob
      : new Blob([fileOrBlob], {type: cleanType});
    const data = new FormData();
    data.append('audio', payload, filename);
    toolCard('ویس دریافت شد', 'در حال تبدیل به متن…');
    setBusy(true);
    try {
      const result = await V4.requestJSON('/api/panel/luna/transcribe', {method: 'POST', body: data});
      input.value = [input.value.trim(), result.text || ''].filter(Boolean).join(' ');
      autoGrow();
      input.focus();
      toolCard('ویس به متن تبدیل شد', 'متن آماده است؛ ارسال را بزن یا قبلش اصلاحش کن', 'success');
      void loadStatus();
    } catch (error) {
      toolCard('تبدیل ویس ناموفق بود', error.message || 'دوباره امتحان کن', 'warning');
    } finally {
      setBusy(false);
      if (audioInput) audioInput.value = '';
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      if (audioInput) {
        audioInput.click();
        V4.toast('ضبط مستقیم مرورگر در HTTP در دسترس نیست؛ ویس را از گوشی انتخاب یا ضبط کن.');
      } else {
        V4.toast('مرورگر این دستگاه ضبط ویس را پشتیبانی نمی‌کند.', 'error');
      }
      return;
    }
    try {
      recordingStream = await navigator.mediaDevices.getUserMedia({audio: true});
      audioChunks = [];
      const mimeType = preferredAudioMime();
      recorder = mimeType ? new MediaRecorder(recordingStream, {mimeType}) : new MediaRecorder(recordingStream);
      recorder.addEventListener('dataavailable', event => {
        if (event.data?.size) audioChunks.push(event.data);
      });
      recorder.addEventListener('stop', () => {
        const recordedType = recorder.mimeType || mimeType || 'audio/webm';
        const cleanType = recordedType.split(';', 1)[0];
        const ext = cleanType.includes('mp4') ? 'mp4' : 'webm';
        const blob = new Blob(audioChunks, {type: cleanType});
        recordingStream?.getTracks().forEach(track => track.stop());
        recordingStream = null;
        mic.classList.remove('is-recording');
        mic.setAttribute('aria-label', 'صحبت با Luna');
        if (blob.size) void transcribeAudio(blob, `luna-voice.${ext}`);
      }, {once: true});
      recorder.start();
      mic.classList.add('is-recording');
      mic.setAttribute('aria-label', 'پایان ضبط');
      if (status) status.textContent = 'دارم گوش می‌دم… برای پایان دوباره میکروفون رو بزن';
    } catch (_) {
      recordingStream?.getTracks().forEach(track => track.stop());
      recordingStream = null;
      recorder = null;
      if (audioInput) {
        audioInput.click();
        V4.toast('مرورگر اجازه ضبط مستقیم نداد؛ ویس را از گوشی انتخاب یا ضبط کن.');
      } else {
        V4.toast('اجازه میکروفون داده نشد یا ضبط شروع نشد.', 'error');
      }
    }
  }

  function stopRecording() {
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (status) status.textContent = 'دستیار هوشمند اتاق خبر بی‌خبر';
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    void ask();
  });

  input.addEventListener('input', autoGrow);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  imageInput.addEventListener('change', () => {
    const file = imageInput.files?.[0];
    if (!file) return clearImage();
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      clearImage();
      V4.toast('فقط JPG، PNG و WebP پشتیبانی می‌شود.', 'error');
      return;
    }
    previewImage(file);
  });

  audioInput?.addEventListener('change', () => {
    const file = audioInput.files?.[0];
    if (!file) return;
    void transcribeAudio(file, file.name || 'luna-voice.m4a');
  });

  mic.addEventListener('click', () => {
    if (recorder && recorder.state !== 'inactive') stopRecording();
    else void startRecording();
  });

  autoGrow();
  void loadStatus();
})();