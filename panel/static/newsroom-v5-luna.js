(() => {
  'use strict';

  const ENDPOINTS = {
    chat: '/api/panel/luna/operator-chat',
    confirm: id => `/api/panel/luna/operator-confirm/${encodeURIComponent(id)}`,
    cancel: id => `/api/panel/luna/operator-cancel/${encodeURIComponent(id)}`,
    history: '/api/panel/luna/operator-history',
    transcribe: '/api/panel/luna/transcribe',
    storyContext: id => `/api/v5/luna/context/story/${encodeURIComponent(id)}`,
    clearStoryContext: '/api/v5/luna/context/story',
  };
  const VOICE_STATES = ['idle', 'recording', 'transcribing', 'transcript-ready', 'error'];
  const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
  const MAX_RECORDING_MS = 120000;
  const GREETING = 'من Luna هستم. طبیعی حرف بزن؛ خبر و منبع رو مدیریت می‌کنم، عکس رو بررسی می‌کنم و ویست رو متن می‌کنم.';

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  async function requestJSON(url, options = {}) {
    let response;
    try {
      response = await fetch(url, {
        credentials: 'same-origin',
        cache: 'no-store',
        ...options,
        headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken(), ...(options.headers || {}) },
      });
    } catch (_) {
      const error = new Error('اتصال برقرار نشد؛ دوباره امتحان کن.');
      error.status = 0;
      error.payload = {};
      error.retryable = true;
      throw error;
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      const error = new Error(payload.reply_fa || payload.message || 'Luna فعلاً در دسترس نیست.');
      error.status = response.status;
      error.payload = payload;
      error.retryable = Boolean(payload.retryable) || response.status >= 500 || response.status === 0;
      throw error;
    }
    return payload;
  }

  function preferredAudioMime() {
    const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
    return options.find(type => window.MediaRecorder?.isTypeSupported?.(type)) || '';
  }

  function formatElapsed(ms) {
    const seconds = Math.floor(ms / 1000);
    const text = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    return text.replace(/\d/g, digit => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]);
  }

  class LunaMessenger {
    constructor(root, { draftKey = 'v5.lunaDraft', toast = () => {}, onActivity = () => {} } = {}) {
      this.root = root;
      this.draftKey = draftKey;
      this.toast = toast;
      this.onActivity = onActivity;
      const q = name => root.querySelector(`[data-luna="${name}"]`);
      this.els = {
        messages: q('messages'),
        form: q('composer'),
        input: q('input'),
        send: q('send'),
        image: q('image'),
        imagePreview: q('image-preview'),
        mic: q('mic'),
        audio: q('audio'),
        voice: q('voice'),
        voiceStatus: q('voice-status'),
        voiceTimer: q('voice-timer'),
        voiceLevel: q('voice-level'),
        voiceCancel: q('voice-cancel'),
        storyChip: q('story-chip'),
        storyTitle: q('story-title'),
        storyClear: q('story-clear'),
      };
      this.busy = false;
      this.selectedImage = null;
      this.voiceState = 'idle';
      this.recorder = null;
      this.stream = null;
      this.chunks = [];
      this.cancelled = false;
      this.timer = null;
      this.levelFrame = null;
      this.audioContext = null;
      this.recordingStartedAt = 0;
      this.autoStop = null;
    }

    start() {
      const { form, input, image, audio, mic, voiceCancel, storyClear } = this.els;
      if (!form || !input || !this.els.messages) return this;
      form.addEventListener('submit', event => { event.preventDefault(); void this.send(); });
      input.addEventListener('input', () => { this.saveDraft(); this.autoGrow(); });
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          form.requestSubmit();
        }
      });
      image?.addEventListener('change', () => this.onImageSelected());
      audio?.addEventListener('change', () => {
        const file = audio.files?.[0];
        if (file) void this.transcribe(file, file.name || 'luna-voice.m4a');
      });
      mic?.addEventListener('click', () => this.toggleRecording());
      voiceCancel?.addEventListener('click', () => this.cancelRecording());
      storyClear?.addEventListener('click', () => void this.clearStoryContext());
      this.restoreDraft();
      this.setVoiceState('idle');
      void this.loadHistory();
      return this;
    }

    // ---- conversation rendering: only user/Luna messages, one inline confirmation, compact errors ----

    scrollToBottom() {
      const { messages } = this.els;
      messages.scrollTop = messages.scrollHeight;
    }

    appendMessage(text, role = 'luna') {
      const article = document.createElement('article');
      article.className = `v5-luna-msg is-${role}`;
      article.dataset.role = role;
      const body = document.createElement('div');
      body.className = 'v5-luna-bubble';
      body.textContent = text;
      article.appendChild(body);
      this.els.messages.appendChild(article);
      this.scrollToBottom();
      return article;
    }

    appendTyping() {
      const article = this.appendMessage('', 'luna');
      article.classList.add('is-typing');
      article.firstChild.innerHTML = '<span class="v5-luna-typing" aria-label="Luna در حال پاسخ است"><i></i><i></i><i></i></span>';
      return article;
    }

    renderReply(article, text) {
      article.classList.remove('is-typing');
      article.firstChild.textContent = text;
      this.scrollToBottom();
    }

    renderError(article, text, retry) {
      article.classList.remove('is-typing');
      article.classList.add('is-error');
      article.dataset.role = 'error';
      const body = article.firstChild;
      body.textContent = text;
      if (retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'v5-luna-retry';
        button.textContent = 'تلاش دوباره';
        button.addEventListener('click', () => { article.remove(); retry(); }, { once: true });
        body.appendChild(button);
      }
      this.scrollToBottom();
    }

    renderConfirmation({ action_id: actionId, summary_fa: summary }) {
      this.els.messages.querySelectorAll('.v5-luna-confirm').forEach(node => node.remove());
      const card = document.createElement('div');
      card.className = 'v5-luna-confirm';
      card.dataset.actionId = actionId;
      card.setAttribute('role', 'group');
      card.setAttribute('aria-label', 'تأیید عملیات');
      const text = document.createElement('p');
      text.textContent = summary || 'این عملیات اجرا شود؟';
      const actions = document.createElement('div');
      actions.className = 'v5-luna-confirm-actions';
      const accept = document.createElement('button');
      accept.type = 'button';
      accept.className = 'v5-primary';
      accept.dataset.confirm = 'accept';
      accept.textContent = 'تأیید و اجرا';
      const reject = document.createElement('button');
      reject.type = 'button';
      reject.className = 'v5-secondary';
      reject.dataset.confirm = 'cancel';
      reject.textContent = 'انصراف';
      actions.append(accept, reject);
      card.append(text, actions);
      accept.addEventListener('click', () => void this.acceptConfirmation(card, actionId));
      reject.addEventListener('click', () => void this.cancelConfirmation(card, actionId));
      this.els.messages.appendChild(card);
      this.scrollToBottom();
    }

    async acceptConfirmation(card, actionId) {
      card.querySelectorAll('button').forEach(button => { button.disabled = true; });
      card.classList.add('is-busy');
      try {
        const result = await requestJSON(ENDPOINTS.confirm(actionId), { method: 'POST' });
        card.remove();
        this.appendMessage(result.reply_fa || 'چشم، انجام شد.', 'luna');
        if (result.pull_request?.url) this.appendBuilderLink(result.pull_request);
        this.onActivity('confirmed', result);
      } catch (error) {
        card.remove();
        const article = this.appendMessage('', 'luna');
        // The server claims a proposal exactly once, so retrying a network failure cannot double-execute.
        const retry = error.retryable && !error.payload?.error ? () => this.renderConfirmation({ action_id: actionId, summary_fa: card.querySelector('p')?.textContent }) : null;
        this.renderError(article, error.message || 'این عملیات انجام نشد.', retry);
      }
    }

    async cancelConfirmation(card, actionId) {
      card.remove();
      try {
        const result = await requestJSON(ENDPOINTS.cancel(actionId), { method: 'POST' });
        this.appendMessage(result.reply_fa || 'باشه، انجامش ندادم.', 'luna');
      } catch (_) {
        this.appendMessage('باشه، انجامش ندادم.', 'luna');
      }
    }

    appendBuilderLink(pr) {
      const article = this.appendMessage(pr.number ? `Draft PR #${pr.number} آماده است.` : 'Draft PR آماده است.', 'luna');
      const link = document.createElement('a');
      link.href = pr.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.className = 'v5-luna-link';
      link.textContent = 'باز کردن PR';
      article.firstChild.appendChild(link);
    }

    async loadHistory() {
      try {
        const data = await requestJSON(ENDPOINTS.history);
        const { messages } = this.els;
        messages.replaceChildren();
        const rows = Array.isArray(data.messages) ? data.messages : [];
        if (!rows.length) this.appendMessage(GREETING, 'luna');
        for (const row of rows) this.appendMessage(row.content, row.role === 'user' ? 'user' : 'luna');
        this.renderStoryChip(data.context?.story || null);
        if (data.context?.pending?.action_id) this.renderConfirmation(data.context.pending);
      } catch (_) {
        if (!this.els.messages.children.length) this.appendMessage(GREETING, 'luna');
      }
    }

    renderStoryChip(story) {
      const { storyChip, storyTitle } = this.els;
      if (!storyChip) return;
      storyChip.hidden = !story;
      if (story && storyTitle) storyTitle.textContent = story.title_fa || 'خبر انتخاب‌شده';
    }

    async setStoryContext(story) {
      if (!story?.id) return;
      this.renderStoryChip({ title_fa: story.title_fa || '' });
      try {
        const result = await requestJSON(ENDPOINTS.storyContext(story.id), { method: 'POST' });
        this.renderStoryChip(result.story);
      } catch (error) {
        this.renderStoryChip(null);
        this.toast(error.message || 'انتخاب خبر برای Luna ممکن نشد.', 'error');
      }
    }

    async clearStoryContext() {
      this.renderStoryChip(null);
      try { await requestJSON(ENDPOINTS.clearStoryContext, { method: 'DELETE' }); } catch (_) {}
    }

    // ---- composer ----

    saveDraft() {
      try { window.sessionStorage.setItem(this.draftKey, this.els.input.value || ''); } catch (_) {}
    }

    restoreDraft() {
      try {
        const draft = window.sessionStorage.getItem(this.draftKey);
        if (draft && !this.els.input.value) this.els.input.value = draft;
      } catch (_) {}
      this.autoGrow();
    }

    autoGrow() {
      const { input } = this.els;
      input.style.height = 'auto';
      input.style.height = `${Math.min(160, Math.max(44, input.scrollHeight))}px`;
    }

    setBusy(value) {
      this.busy = Boolean(value);
      const { send, image, audio, mic } = this.els;
      if (send) send.disabled = this.busy;
      if (image) image.disabled = this.busy;
      if (audio) audio.disabled = this.busy;
      if (mic && this.voiceState !== 'recording') mic.disabled = this.busy || this.voiceState === 'transcribing';
    }

    onImageSelected() {
      const file = this.els.image.files?.[0];
      if (!file) return this.clearImage();
      if (!IMAGE_TYPES.includes(file.type)) {
        this.clearImage();
        this.toast('فقط JPG، PNG و WebP پشتیبانی می‌شود.', 'error');
        return undefined;
      }
      this.selectedImage = file;
      const preview = this.els.imagePreview;
      if (!preview) return undefined;
      const url = URL.createObjectURL(file);
      const img = document.createElement('img');
      img.src = url;
      img.alt = 'پیش‌نمایش تصویر';
      img.onload = () => URL.revokeObjectURL(url);
      const label = document.createElement('span');
      label.textContent = file.name || 'تصویر پیوست شد';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'v5-luna-chip-remove';
      remove.textContent = '×';
      remove.setAttribute('aria-label', 'حذف تصویر');
      remove.addEventListener('click', () => this.clearImage(), { once: true });
      preview.replaceChildren(img, label, remove);
      preview.hidden = false;
      return undefined;
    }

    clearImage() {
      this.selectedImage = null;
      if (this.els.image) this.els.image.value = '';
      if (this.els.imagePreview) {
        this.els.imagePreview.hidden = true;
        this.els.imagePreview.replaceChildren();
      }
    }

    async send(retryPayload = null) {
      const { input } = this.els;
      const text = retryPayload ? retryPayload.text : String(input.value || '').trim();
      const image = retryPayload ? retryPayload.image : this.selectedImage;
      if ((!text && !image) || this.busy) return;
      if (!retryPayload) {
        this.appendMessage(text || 'این تصویر رو بررسی کن', 'user');
        input.value = '';
        this.saveDraft();
        this.autoGrow();
        this.clearImage();
        if (this.voiceState === 'transcript-ready' || this.voiceState === 'error') this.setVoiceState('idle');
      }
      this.setBusy(true);
      const pending = this.appendTyping();
      try {
        const data = new FormData();
        data.append('message', text);
        if (image) data.append('image', image, image.name || 'image.jpg');
        const result = await requestJSON(ENDPOINTS.chat, { method: 'POST', body: data });
        if (result.confirmation_required && result.action_id) {
          pending.remove();
          this.renderConfirmation(result);
        } else {
          this.renderReply(pending, result.reply_fa || 'پاسخی دریافت نشد.');
        }
        this.onActivity('reply', result);
      } catch (error) {
        const retry = error.retryable ? () => void this.send({ text, image }) : null;
        this.renderError(pending, error.message || 'Luna فعلاً نتوانست پاسخ بدهد.', retry);
      } finally {
        this.setBusy(false);
        input.focus();
      }
    }

    // ---- voice: idle → recording → transcribing → transcript-ready | error ----

    setVoiceState(state, detail = '') {
      if (!VOICE_STATES.includes(state)) return;
      this.voiceState = state;
      const { voice, voiceStatus, voiceTimer, voiceCancel, mic } = this.els;
      this.root.dataset.voiceState = state;
      if (voice) {
        voice.dataset.state = state;
        voice.hidden = state === 'idle';
      }
      const labels = {
        idle: '',
        recording: 'در حال ضبط… برای پایان دوباره میکروفون را بزن',
        transcribing: 'در حال تبدیل صدا به متن…',
        'transcript-ready': 'متن آماده است؛ اصلاح کن و بفرست',
        error: detail || 'تبدیل صدا ناموفق بود؛ دوباره امتحان کن',
      };
      if (voiceStatus) voiceStatus.textContent = labels[state];
      if (voiceTimer) voiceTimer.hidden = state !== 'recording';
      if (voiceCancel) voiceCancel.hidden = state !== 'recording';
      if (mic) {
        mic.classList.toggle('is-recording', state === 'recording');
        mic.setAttribute('aria-pressed', state === 'recording' ? 'true' : 'false');
        mic.setAttribute('aria-label', state === 'recording' ? 'پایان ضبط' : 'ضبط صدا');
        mic.disabled = state === 'transcribing' || (this.busy && state !== 'recording');
      }
    }

    toggleRecording() {
      if (this.voiceState === 'recording') this.stopRecording();
      else if (this.voiceState !== 'transcribing') void this.startRecording();
    }

    useAudioFileFallback(reason) {
      if (this.els.audio) {
        this.els.audio.click();
        this.toast(reason);
      } else {
        this.setVoiceState('error', 'این مرورگر ضبط صدا را پشتیبانی نمی‌کند.');
      }
    }

    async startRecording() {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        this.useAudioFileFallback('ضبط مستقیم در این مرورگر یا بدون HTTPS در دسترس نیست؛ فایل صوتی را انتخاب یا ضبط کن.');
        return;
      }
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (_) {
        this.stream = null;
        this.useAudioFileFallback('اجازه میکروفون داده نشد؛ فایل صوتی را انتخاب یا ضبط کن.');
        return;
      }
      this.chunks = [];
      this.cancelled = false;
      const mimeType = preferredAudioMime();
      this.recorder = mimeType ? new MediaRecorder(this.stream, { mimeType }) : new MediaRecorder(this.stream);
      this.recorder.addEventListener('dataavailable', event => { if (event.data?.size) this.chunks.push(event.data); });
      this.recorder.addEventListener('stop', () => this.onRecordingStopped(mimeType), { once: true });
      this.recorder.start();
      this.recordingStartedAt = Date.now();
      this.setVoiceState('recording');
      this.startMeters();
      this.autoStop = window.setTimeout(() => this.stopRecording(), MAX_RECORDING_MS);
    }

    startMeters() {
      const { voiceTimer, voiceLevel } = this.els;
      const tick = () => { if (voiceTimer) voiceTimer.textContent = formatElapsed(Date.now() - this.recordingStartedAt); };
      tick();
      this.timer = window.setInterval(tick, 250);
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!voiceLevel || !AudioContextClass || !this.stream) return;
      try {
        this.audioContext = new AudioContextClass();
        const analyser = this.audioContext.createAnalyser();
        analyser.fftSize = 256;
        this.audioContext.createMediaStreamSource(this.stream).connect(analyser);
        const samples = new Uint8Array(analyser.frequencyBinCount);
        const draw = () => {
          analyser.getByteTimeDomainData(samples);
          let peak = 0;
          for (const value of samples) peak = Math.max(peak, Math.abs(value - 128));
          voiceLevel.style.setProperty('--level', String(Math.min(1, peak / 64)));
          this.levelFrame = window.requestAnimationFrame(draw);
        };
        draw();
      } catch (_) {
        this.audioContext = null;
      }
    }

    stopMeters() {
      window.clearInterval(this.timer);
      window.clearTimeout(this.autoStop);
      if (this.levelFrame) window.cancelAnimationFrame(this.levelFrame);
      this.levelFrame = null;
      this.audioContext?.close?.().catch?.(() => {});
      this.audioContext = null;
      this.els.voiceLevel?.style.setProperty('--level', '0');
    }

    releaseStream() {
      this.stream?.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    stopRecording() {
      if (this.recorder && this.recorder.state !== 'inactive') this.recorder.stop();
    }

    cancelRecording() {
      this.cancelled = true;
      this.stopRecording();
      this.stopMeters();
      this.releaseStream();
      this.chunks = [];
      this.setVoiceState('idle');
    }

    onRecordingStopped(mimeType) {
      this.stopMeters();
      this.releaseStream();
      const recorded = String(this.recorder?.mimeType || mimeType || 'audio/webm').split(';', 1)[0];
      this.recorder = null;
      if (this.cancelled) return;
      const blob = new Blob(this.chunks, { type: recorded });
      this.chunks = [];
      if (!blob.size) {
        this.setVoiceState('error', 'صدایی ضبط نشد.');
        return;
      }
      void this.transcribe(blob, `luna-voice.${recorded.includes('mp4') ? 'mp4' : 'webm'}`);
    }

    async transcribe(fileOrBlob, filename) {
      this.setVoiceState('transcribing');
      const cleanType = String(fileOrBlob?.type || 'audio/webm').split(';', 1)[0] || 'audio/webm';
      const payload = fileOrBlob instanceof File ? fileOrBlob : new Blob([fileOrBlob], { type: cleanType });
      const data = new FormData();
      data.append('audio', payload, filename);
      try {
        const result = await requestJSON(ENDPOINTS.transcribe, { method: 'POST', body: data });
        const text = String(result.text || '').trim();
        if (!text) {
          this.setVoiceState('error', 'متنی از صدا تشخیص داده نشد.');
          return;
        }
        const { input } = this.els;
        input.value = [input.value.trim(), text].filter(Boolean).join(' ');
        this.saveDraft();
        this.autoGrow();
        input.focus();
        this.setVoiceState('transcript-ready');
      } catch (error) {
        this.setVoiceState('error', error.message || 'تبدیل صدا ناموفق بود؛ دوباره امتحان کن');
      } finally {
        if (this.els.audio) this.els.audio.value = '';
      }
    }
  }

  function mount(root, options) {
    if (!root) return null;
    return new LunaMessenger(root, options).start();
  }

  window.NewsroomV5Luna = { LunaMessenger, ENDPOINTS, VOICE_STATES, mount, requestJSON };
})();
