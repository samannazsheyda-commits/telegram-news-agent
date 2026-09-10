(() => {
  const modules = document.querySelector('.newsroom-modules, .premium-modules');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (!modules || !csrf) return;

  const wrapper = document.createElement('section');
  wrapper.className = 'agent-settings-wrap';
  wrapper.innerHTML = `
    <div class="section-head settings-heading">
      <div><span class="section-kicker">تنظیمات</span><h2>تنظیمات ایجنت</h2></div>
      <small>هر تغییر بعد از ذخیره در چرخه بعدی ایجنت اعمال می‌شود.</small>
    </div>
    <form id="agentSettingsForm" class="agent-settings-card">
      <label class="setting-field">
        <span>حداکثر سن خبر</span>
        <div class="setting-control"><input id="freshnessHours" type="number" min="1" max="48" inputmode="numeric" value="3"><em>ساعت</em></div>
        <small>خبر قدیمی‌تر از این بازه وارد انتشار خودکار نمی‌شود.</small>
      </label>
      <label class="setting-field setting-toggle-field">
        <span>حالت سکوت انتشار</span>
        <input id="quietMode" type="checkbox" class="switch-input">
        <i class="switch-ui" aria-hidden="true"></i>
        <small>در این بازه خبر جمع می‌شود اما خودکار منتشر نمی‌شود.</small>
      </label>
      <label class="setting-field">
        <span>شروع سکوت</span>
        <input id="quietStart" type="time" value="00:00">
        <small>بر اساس ساعت تهران</small>
      </label>
      <label class="setting-field">
        <span>پایان سکوت</span>
        <input id="quietEnd" type="time" value="07:00">
        <small>بر اساس ساعت تهران</small>
      </label>
      <div class="setting-field readonly-setting">
        <span>فاصله رصد ایجنت</span>
        <strong>۲ ثانیه</strong>
        <small>برای سرعت و پایداری سرویس از این صفحه قابل تغییر نیست.</small>
      </div>
      <div class="settings-actions">
        <span id="settingsResult">در حال دریافت تنظیمات…</span>
        <button id="saveAgentSettings" class="button primary-action" type="submit" disabled>ذخیره تغییرات</button>
      </div>
    </form>`;
  modules.insertAdjacentElement('afterend', wrapper);

  const form = wrapper.querySelector('#agentSettingsForm');
  const freshness = wrapper.querySelector('#freshnessHours');
  const quietMode = wrapper.querySelector('#quietMode');
  const quietStart = wrapper.querySelector('#quietStart');
  const quietEnd = wrapper.querySelector('#quietEnd');
  const result = wrapper.querySelector('#settingsResult');
  const save = wrapper.querySelector('#saveAgentSettings');
  let baseline = '';

  function snapshot() {
    return JSON.stringify({
      freshness_hours: Number(freshness.value),
      quiet_mode: quietMode.checked,
      quiet_start: quietStart.value,
      quiet_end: quietEnd.value,
    });
  }

  function syncDirty() {
    const dirty = snapshot() !== baseline;
    save.disabled = !dirty;
    if (dirty) {
      result.textContent = 'تغییر ذخیره‌نشده داری.';
      result.classList.remove('settings-error');
    } else if (baseline) {
      result.textContent = 'تنظیمات همگام است.';
    }
  }

  async function loadSettings() {
    try {
      const response = await fetch('/api/command-center/status', {credentials:'same-origin', cache:'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const settings = data.settings || {};
      freshness.value = Number(settings.freshness_hours || 3);
      quietMode.checked = Boolean(settings.quiet_mode);
      quietStart.value = settings.quiet_start || '00:00';
      quietEnd.value = settings.quiet_end || '07:00';
      baseline = snapshot();
      save.disabled = true;
      result.textContent = 'تنظیمات همگام است.';
      result.classList.remove('settings-error');
    } catch (_) {
      result.textContent = 'دریافت تنظیمات ناموفق بود.';
      result.classList.add('settings-error');
    }
  }

  [freshness, quietMode, quietStart, quietEnd].forEach(input => input.addEventListener('input', syncDirty));
  quietMode.addEventListener('change', syncDirty);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (save.disabled) return;
    save.disabled = true;
    result.textContent = 'در حال ذخیره…';
    result.classList.remove('settings-error');
    try {
      const payload = JSON.parse(snapshot());
      const response = await fetch('/api/command-center/settings', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type':'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
      baseline = snapshot();
      result.textContent = `ذخیره شد · ${new Date().toLocaleTimeString('fa-IR', {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
    } catch (error) {
      result.textContent = error.message === 'invalid_settings' ? 'مقادیر تنظیمات معتبر نیست.' : `خطا: ${error.message}`;
      result.classList.add('settings-error');
    } finally {
      save.disabled = snapshot() === baseline;
    }
  });

  loadSettings();
})();