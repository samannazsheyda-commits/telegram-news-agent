(() => {
  const form = document.getElementById('lunaForm');
  if (!form) return;
  const messages = document.getElementById('lunaMessages');
  const input = document.getElementById('lunaMessage');
  const story = document.getElementById('lunaStoryId');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const append = (role, text) => {
    const item = document.createElement('div');
    item.className = `luna-message ${role}`;
    item.textContent = text;
    messages.appendChild(item);
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const prompt = input.value.trim();
    if (!prompt) return;
    append('user', prompt);
    input.value = '';
    const response = await fetch('/api/luna/chat', {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({message:prompt,story_id:story.value.trim() || null})});
    const data = await response.json();
    append(response.ok ? 'assistant' : 'error', data.text || data.error || 'خطای Luna');
  });
  const voiceButton = document.getElementById('lunaVoice');
  let activeRecorder = null;
  voiceButton.addEventListener('click', async () => {
    if (activeRecorder) {
      activeRecorder.stop();
      activeRecorder = null;
      voiceButton.textContent = 'پیام صوتی';
      return;
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) return append('error', 'ضبط صدا در این مرورگر پشتیبانی نمی‌شود.');
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    const recorder = new MediaRecorder(stream);
    activeRecorder = recorder;
    const chunks = [];
    recorder.ondataavailable = event => chunks.push(event.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      const formData = new FormData();
      formData.append('voice', new Blob(chunks, {type:recorder.mimeType}), 'voice.webm');
      const response = await fetch('/api/luna/voice', {method:'POST',headers:{'X-CSRFToken':csrf},body:formData});
      const data = await response.json();
      if (response.ok) input.value = data.transcript; else append('error', data.error || 'خطای تبدیل صدا');
    };
    recorder.start();
    voiceButton.textContent = 'پایان ضبط';
    append('assistant', 'ضبط شروع شد؛ برای پایان دوباره دکمه را بزن.');
  });
})();
