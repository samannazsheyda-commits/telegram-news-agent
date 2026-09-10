(() => {
  const anchor = document.getElementById('agentSettingsAnchor');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (!anchor || !csrf) return;

  const wrapper = document.createElement('section');
  wrapper.className = 'agent-settings-wrap';
  wrapper.innerHTML = `
    <details class="agent-settings-details">
      <summary><span>⚙️ تنظیمات ایجنت</span><small>سن خبر، حالت سکوت و فاصله رصد</small></summary>
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
        <label class="setting-field"><span>شروع سکوت</span><input id="quietStart" type="time" value="00:00"><small>ساعت تهران</small></label>
        <label class="setting-field"><span>پایان سکوت</span><input id="quietEnd" type="time" value="07:00"><small>ساعت تهران</small></label>
        <div class="setting-field readonly-setting"><span>فاصله رصد ایجنت</span><strong>۲ ثانیه</strong><small>برای سرعت و پایداری production ثابت است.</small></div>
        <div class="settings-actions">
          <span id="settingsResult">در حال دریافت تنظیمات…</span>
          <button id="saveAgentSettings" class="button primary-action" type="submit" disabled>ذخیره تغییرات</button>
        </div>
      </form>
    </details>`;
  anchor.appendChild(wrapper);

  const form = wrapper.querySelector('#agentSettingsForm');
  const freshness = wrapper.querySelector('#freshnessHours');
  const quietMode = wrapper.querySelector('#quietMode');
  const quietStart = wrapper.querySelector('#quietStart');
  const quietEnd = wrapper.querySelector('#quietEnd');
  const result = wrapper.querySelector('#settingsResult');
  const save = wrapper.querySelector('#saveAgentSettings');

  const priorityList = document.getElementById('priorityRulesList');
  const priorityInput = document.getElementById('priorityRuleInput');
  const priorityAdd = document.getElementById('priorityRuleAdd');
  const prioritySave = document.getElementById('priorityRulesSave');
  const priorityResult = document.getElementById('priorityRulesResult');

  let priorityRules = [];
  let priorityBaseline = '';
  let settingsBaseline = '';

  function settingsSnapshot() {
    return JSON.stringify({
      freshness_hours: Number(freshness.value),
      quiet_mode: quietMode.checked,
      quiet_start: quietStart.value,
      quiet_end: quietEnd.value,
    });
  }

  function prioritySnapshot() {
    return JSON.stringify(priorityRules);
  }

  function fullPayload() {
    return {
      ...JSON.parse(settingsSnapshot()),
      priority_rules: [...priorityRules],
    };
  }

  function syncSettingsDirty() {
    const dirty = settingsSnapshot() !== settingsBaseline;
    save.disabled = !dirty;
    if (dirty) {
      result.textContent = 'تغییر ذخیره‌نشده داری.';
      result.classList.remove('settings-error');
    } else if (settingsBaseline) {
      result.textContent = 'تنظیمات همگام است.';
    }
  }

  function syncPriorityDirty() {
    if (!prioritySave) return;
    const dirty = prioritySnapshot() !== priorityBaseline;
    prioritySave.disabled = !dirty || priorityRules.length === 0;
    if (priorityResult) priorityResult.textContent = dirty ? 'تغییرات اولویت هنوز ذخیره نشده.' : 'اولویت‌ها همگام‌اند.';
  }

  function priorityButton(text, title, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'priority-rule-button';
    button.textContent = text;
    button.title = title;
    button.addEventListener('click', handler);
    return button;
  }

  function renderPriorities() {
    if (!priorityList) return;
    priorityList.replaceChildren();
    priorityRules.forEach((rule, index) => {
      const row = document.createElement('div');
      row.className = 'priority-rule-row';
      const order = document.createElement('b'); order.textContent = (index + 1).toLocaleString('fa-IR');
      const text = document.createElement('span'); text.textContent = rule;
      const actions = document.createElement('div'); actions.className = 'priority-rule-actions';
      actions.append(
        priorityButton('↑', 'بالاتر', () => { if (index > 0) { [priorityRules[index - 1], priorityRules[index]] = [priorityRules[index], priorityRules[index - 1]]; renderPriorities(); } }),
        priorityButton('↓', 'پایین‌تر', () => { if (index < priorityRules.length - 1) { [priorityRules[index + 1], priorityRules[index]] = [priorityRules[index], priorityRules[index + 1]]; renderPriorities(); } }),
        priorityButton('×', 'حذف', () => { priorityRules.splice(index, 1); renderPriorities(); })
      );
      row.append(order, text, actions);
      priorityList.appendChild(row);
    });
    syncPriorityDirty();
  }

  async function saveSettings(payload) {
    const response = await fetch('/api/command-center/settings', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type':'application/json', 'X-CSRFToken': csrf},
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data.settings || {};
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
      priorityRules = Array.isArray(settings.priority_rules) ? settings.priority_rules.map(value => String(value || '').trim()).filter(Boolean) : [];
      settingsBaseline = settingsSnapshot();
      priorityBaseline = prioritySnapshot();
      save.disabled = true;
      result.textContent = 'تنظیمات همگام است.';
      result.classList.remove('settings-error');
      renderPriorities();
    } catch (_) {
      result.textContent = 'دریافت تنظیمات ناموفق بود.';
      result.classList.add('settings-error');
      if (priorityResult) priorityResult.textContent = 'دریافت اولویت‌ها ناموفق بود.';
    }
  }

  [freshness, quietMode, quietStart, quietEnd].forEach(input => input.addEventListener('input', syncSettingsDirty));
  quietMode.addEventListener('change', syncSettingsDirty);

  priorityAdd?.addEventListener('click', () => {
    const value = String(priorityInput?.value || '').replace(/\s+/g, ' ').trim();
    if (value.length < 2 || value.length > 120) {
      if (priorityResult) priorityResult.textContent = 'عبارت باید بین ۲ تا ۱۲۰ نویسه باشد.';
      return;
    }
    if (priorityRules.some(rule => rule.localeCompare(value, 'fa', {sensitivity:'base'}) === 0)) {
      if (priorityResult) priorityResult.textContent = 'این عبارت قبلاً وجود دارد.';
      return;
    }
    if (priorityRules.length >= 40) {
      if (priorityResult) priorityResult.textContent = 'حداکثر ۴۰ عبارت قابل ثبت است.';
      return;
    }
    priorityRules.push(value);
    if (priorityInput) priorityInput.value = '';
    renderPriorities();
  });
  priorityInput?.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); priorityAdd?.click(); } });

  prioritySave?.addEventListener('click', async () => {
    prioritySave.disabled = true;
    if (priorityResult) priorityResult.textContent = 'در حال ذخیره اولویت‌ها…';
    try {
      const settings = await saveSettings(fullPayload());
      priorityRules = Array.isArray(settings.priority_rules) ? settings.priority_rules : priorityRules;
      priorityBaseline = prioritySnapshot();
      settingsBaseline = settingsSnapshot();
      renderPriorities();
      if (priorityResult) priorityResult.textContent = 'اولویت‌ها ذخیره شد و از چرخه بعدی روی ترتیب خبرها اثر می‌گذارد.';
    } catch (error) {
      if (priorityResult) priorityResult.textContent = error.message === 'invalid_settings' ? 'یکی از اولویت‌ها معتبر نیست.' : `خطا: ${error.message}`;
      prioritySave.disabled = false;
    }
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (save.disabled) return;
    save.disabled = true;
    result.textContent = 'در حال ذخیره…';
    result.classList.remove('settings-error');
    try {
      const settings = await saveSettings(fullPayload());
      settingsBaseline = settingsSnapshot();
      priorityRules = Array.isArray(settings.priority_rules) ? settings.priority_rules : priorityRules;
      priorityBaseline = prioritySnapshot();
      renderPriorities();
      result.textContent = `ذخیره شد · ${new Date().toLocaleTimeString('fa-IR', {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
    } catch (error) {
      result.textContent = error.message === 'invalid_settings' ? 'مقادیر تنظیمات معتبر نیست.' : `خطا: ${error.message}`;
      result.classList.add('settings-error');
    } finally {
      save.disabled = settingsSnapshot() === settingsBaseline;
    }
  });

  loadSettings();
})();