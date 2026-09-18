(() => {
  const form = document.getElementById('v4LunaComposer');
  const input = document.getElementById('v4LunaInput');
  const messages = document.getElementById('v4LunaMessages');
  const imageInput = document.getElementById('v4LunaImage');
  const imagePreview = document.getElementById('v4LunaAttachmentPreview');
  const mic = document.getElementById('v4LunaMic');
  const send = document.getElementById('v4LunaSend');
  const connection = document.getElementById('v4LunaConnection');
  const status = document.getElementById('v4LunaStatus');
  if (!form || !input || !messages || !imageInput || !mic || !send || !window.BikhabarV4) return;

  const V4 = window.BikhabarV4;
  let selectedImage = null;
  let recorder = null;
  let recordingStream = null;
  let audioChunks = [];
  let busy = false;

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

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

  function setBusy(value) {
    busy = Boolean(value);
    send.disabled = busy;
    imageInput.disabled = busy;
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
      const info = await V4.requestJSON('/api/panel/luna/status');
      if (connection) {
        connection.textContent = info.connected ? 'Luna متصل' : 'Luna متصل نیست';
        connection.dataset.connected = info.connected ? '1' : '0';
      }
      if (status) {
        const builder = info.builder_connected ? 'Builder آماده' : 'Builder بدون اتصال GitHub';
        status.textContent = info.connected ? `دستیار اتاق خبر · ${builder}` : 'کلید OpenAI روی سرور تنظیم نشده';
      }
    } catch (_) {
      if (connection) connection.textContent = 'وضعیت نامشخص';
    }
  }

  async function confirmResult(result) {
    if (!result.confirmation_required || !result.action_id) return;
    const accepted = await V4.confirmAction({
      title: result.mode === 'builder' ? 'Luna وارد حالت Builder شود؟' : 'Luna این کار را انجام دهد؟',
      text: result.reply_fa || 'این عملیات نیاز به تأیید دارد.',
      accept: 'تأیید و اجرا',
    });
    if (!accepted) {
      toolCard('عملیات لغو شد', 'هیچ تغییری انجام نشد', 'warning');
      return;
    }
    try {
      const confirmed = await V4.requestJSON(`/api/panel/luna/assistant/confirm/${encodeURIComponent(result.action_id)}`, {method: 'POST'});
      toolCard('انجام شد', confirmed.reply_fa || 'عملیات با تأیید تو اجرا شد.', 'success');
    } catch (error) {
      toolCard('اجرا نشد', error.message || 'این عملیات فعلاً قابل اجرا نیست.', 'warning');
    }
  }

  async function ask() {
    const text = String(input.value || '').trim();
    if ((!text && !selectedImage) || busy) return;

    message(text || 'این تصویر رو بررسی کن', 'user');
    const data = new FormData();
    data.append('message', text);
    if (selectedImage) data.append('image', selectedImage, selectedImage.name || 'image.jpg');
    input.value = '';
    autoGrow();
    clearImage();
    setBusy(true);
    const pending = typing();

    try {
      const result = await V4.requestJSON('/api/panel/luna/chat', {method: 'POST', body: data});
      pending.body.replaceChildren();
      const paragraph = document.createElement('p');
      paragraph.textContent = result.reply_fa || 'انجام شد.';
      pending.body.appendChild(paragraph);
      if (result.mode === 'builder') toolCard('Builder', 'درخواست تغییر کد تشخیص داده شد');
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

  async function transcribeBlob(blob) {
    const mime = blob.type || 'audio/webm';
    const ext = mime.includes('mp4') ? 'mp4' : 'webm';
    const data = new FormData();
    data.append('audio', blob, `luna-voice.${ext}`);
    toolCard('ویس دریافت شد', 'در حال تبدیل به متن…');
    setBusy(true);
    try {
      const result = await V4.requestJSON('/api/panel/luna/transcribe', {method: 'POST', body: data});
      input.value = [input.value.trim(), result.text || ''].filter(Boolean).join(' ');
      autoGrow();
      input.focus();
      toolCard('تبدیل ویس به متن انجام شد', 'متن را قبل از ارسال می‌توانی ویرایش کنی', 'success');
    } catch (error) {
      toolCard('تبدیل ویس ناموفق بود', error.message || 'دوباره امتحان کن', 'warning');
    } finally {
      setBusy(false);
    }
  }

  function preferredAudioMime() {
    const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
    return options.find(type => window.MediaRecorder?.isTypeSupported?.(type)) || '';
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      V4.toast('مرورگر این دستگاه ضبط ویس را پشتیبانی نمی‌کند.', 'error');
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
        const blob = new Blob(audioChunks, {type: recorder.mimeType || mimeType || 'audio/webm'});
        recordingStream?.getTracks().forEach(track => track.stop());
        recordingStream = null;
        mic.classList.remove('is-recording');
        mic.setAttribute('aria-label', 'صحبت با Luna');
        if (blob.size) void transcribeBlob(blob);
      }, {once: true});
      recorder.start();
      mic.classList.add('is-recording');
      mic.setAttribute('aria-label', 'پایان ضبط');
      if (status) status.textContent = 'در حال شنیدن… برای پایان دوباره میکروفون را بزن';
    } catch (error) {
      recordingStream?.getTracks().forEach(track => track.stop());
      recordingStream = null;
      recorder = null;
      V4.toast('اجازه میکروفون داده نشد یا ضبط شروع نشد.', 'error');
    }
  }

  function stopRecording() {
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (status) status.textContent = 'دستیار اتاق خبر بی‌خبر';
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

  mic.addEventListener('click', () => {
    if (recorder && recorder.state !== 'inactive') stopRecording();
    else void startRecording();
  });

  autoGrow();
  void loadStatus();
})();
