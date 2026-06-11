/* Free Agent Academy — Dashboard JS v2 */

const generateBtn   = document.getElementById('generate-btn');
const errorBox      = document.getElementById('error-box');
const resultSection = document.getElementById('result-section');
const modal         = document.getElementById('processing-modal');
const modalBar      = document.getElementById('modal-bar');

const STEPS = [
  { id: 'step-1', pct: 15,  ms: 800  },
  { id: 'step-2', pct: 45,  ms: 4000 },
  { id: 'step-3', pct: 75,  ms: 8000 },
  { id: 'step-4', pct: 92,  ms: 3000 },
];

let stepTimers = [];

if (generateBtn) {
  generateBtn.addEventListener('click', handleGenerate);
}

async function handleGenerate() {
  const url          = document.getElementById('video-url').value.trim();
  const instructions = document.getElementById('instructions').value.trim();

  if (!url) { showError('Por favor introduce la URL del vídeo.'); return; }

  hideError();
  resultSection.classList.add('hidden');
  openModal();

  try {
    const response = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, custom_instructions: instructions }),
    });

    const data = await response.json();
    closeModal();

    if (!response.ok) {
      showError(data.detail || 'Error inesperado. Inténtalo de nuevo.');
      return;
    }

    fillResult(data, url);
    updateQuota(data);
    resultSection.classList.remove('hidden');
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch {
    closeModal();
    showError('Error de conexión. Comprueba tu internet e inténtalo de nuevo.');
  }
}

/* ── Modal ──────────────────────────────────── */
function openModal() {
  resetSteps();
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  generateBtn.disabled = true;
  animateSteps();
}

function closeModal() {
  stepTimers.forEach(clearTimeout);
  stepTimers = [];
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  generateBtn.disabled = false;
}

function resetSteps() {
  if (modalBar) modalBar.style.width = '0%';
  STEPS.forEach(s => {
    const el  = document.getElementById(s.id);
    if (!el) return;
    const dot = el.querySelector('.step-dot');
    el.classList.remove('live', 'done');
    dot.classList.remove('active', 'done');
  });
}

function animateSteps() {
  let elapsed = 0;
  STEPS.forEach((step, i) => {
    const t = setTimeout(() => {
      if (i > 0) {
        const prev = document.getElementById(STEPS[i - 1].id);
        if (prev) {
          prev.querySelector('.step-dot').classList.replace('active', 'done');
          prev.classList.replace('live', 'done');
        }
      }
      const el = document.getElementById(step.id);
      if (el) {
        el.classList.add('live');
        el.querySelector('.step-dot').classList.add('active');
      }
      if (modalBar) modalBar.style.width = step.pct + '%';
    }, elapsed);
    stepTimers.push(t);
    elapsed += step.ms;
  });
}

/* ── Fill result ────────────────────────────── */
function fillResult(data, url) {
  setText('hook-text',    data.hook       || '');
  setText('dev-text',     data.desarrollo || '');
  setText('conc-text',    data.conclusion || '');
  setText('caption-text', data.caption    || '');

  // Source URL
  const urlEl = document.getElementById('result-url');
  if (urlEl) urlEl.textContent = url.length > 55 ? url.slice(0, 55) + '…' : url;

  // Thumbnail
  const thumbImg  = document.getElementById('video-thumb-img');
  const thumbPlch = document.getElementById('thumb-placeholder');
  if (thumbImg && data.thumbnail_path) {
    thumbImg.src = data.thumbnail_path;
    thumbImg.classList.remove('hidden');
    if (thumbPlch) thumbPlch.classList.add('hidden');
  }
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/* ── Quota ──────────────────────────────────── */
function updateQuota(data) {
  if (data.limit === null || data.limit === undefined) return;

  // Chip in header
  const chip = document.querySelector('.quota-chip');
  if (chip && data.remaining !== null && data.remaining !== undefined) {
    const dot = chip.querySelector('.quota-dot');
    chip.classList.remove('low', 'empty');
    const r = data.remaining;
    const s = r === 1 ? '' : 's';
    chip.lastChild.textContent = ` ${r} guión${r !== 1 ? 'es' : ''} restante${s} este mes`;
    if (r === 0) { chip.classList.add('empty'); generateBtn.disabled = true; }
    else if (r <= 3) { chip.classList.add('low'); }
  }

  // Sidebar quota text
  const sidebarQuota = document.querySelector('.user-quota');
  if (sidebarQuota && data.remaining !== null) {
    sidebarQuota.textContent = `${data.remaining} guiones restantes`;
    sidebarQuota.className = 'user-quota';
    if (data.remaining === 0) sidebarQuota.classList.add('empty');
    else if (data.remaining <= 3) sidebarQuota.classList.add('low');
  }
}

/* ── Error ──────────────────────────────────── */
function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove('hidden');
  errorBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function hideError() { errorBox.classList.add('hidden'); }

/* ── Copy buttons (result section) ─────────── */
document.querySelectorAll('.copy-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const el = document.getElementById(btn.dataset.target);
    if (el) copyText(el.textContent, btn);
  });
});

const copyAllBtn = document.getElementById('copy-all-btn');
if (copyAllBtn) {
  copyAllBtn.addEventListener('click', () => {
    const hook    = document.getElementById('hook-text')?.textContent    || '';
    const dev     = document.getElementById('dev-text')?.textContent     || '';
    const conc    = document.getElementById('conc-text')?.textContent    || '';
    const caption = document.getElementById('caption-text')?.textContent || '';
    const all = `🎯 HOOK\n${hook}\n\n📖 DESARROLLO\n${dev}\n\n✅ CONCLUSIÓN\n${conc}\n\n📲 CAPTION\n${caption}`;
    copyText(all, copyAllBtn);
  });
}

/* ── Copy from recent list ──────────────────── */
document.querySelectorAll('.recent-copy-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const text = buildScriptText(btn.dataset.hook, btn.dataset.dev, btn.dataset.conc, btn.dataset.caption);
    copyText(text, btn);
  });
});

function buildScriptText(hook, dev, conc, caption) {
  return `🎯 HOOK\n${hook}\n\n📖 DESARROLLO\n${dev}\n\n✅ CONCLUSIÓN\n${conc}\n\n📲 CAPTION\n${caption}`;
}

/* ── Password change modal ──────────────────── */
const pwdSubmit = document.getElementById('pwd-submit');
if (pwdSubmit) {
  pwdSubmit.addEventListener('click', async () => {
    const newPwd     = document.getElementById('pwd-new').value.trim();
    const confirmPwd = document.getElementById('pwd-confirm').value.trim();
    const errEl      = document.getElementById('pwd-error');

    errEl.classList.add('hidden');

    if (newPwd.length < 8) {
      errEl.textContent = 'La contraseña debe tener al menos 8 caracteres.';
      errEl.classList.remove('hidden');
      return;
    }
    if (newPwd !== confirmPwd) {
      errEl.textContent = 'Las contraseñas no coinciden.';
      errEl.classList.remove('hidden');
      return;
    }

    pwdSubmit.disabled = true;
    pwdSubmit.textContent = 'Guardando…';

    try {
      const res  = await fetch('/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPwd, confirm_password: confirmPwd }),
      });
      const data = await res.json();

      if (!res.ok) {
        errEl.textContent = data.detail || 'Error al guardar la contraseña.';
        errEl.classList.remove('hidden');
        pwdSubmit.disabled = false;
        pwdSubmit.textContent = 'Guardar contraseña';
        return;
      }

      document.getElementById('pwd-modal').remove();
    } catch {
      errEl.textContent = 'Error de conexión. Inténtalo de nuevo.';
      errEl.classList.remove('hidden');
      pwdSubmit.disabled = false;
      pwdSubmit.textContent = 'Guardar contraseña';
    }
  });
}

function copyText(text, btn) {
  const original = btn.textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '¡Copiado!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = original; btn.classList.remove('copied'); }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.textContent = '¡Copiado!';
    setTimeout(() => { btn.textContent = original; }, 2000);
  });
}
