/* Free Agent Academy — Dashboard JS */

const generateBtn   = document.getElementById('generate-btn');
const errorBox      = document.getElementById('error-box');
const resultSection = document.getElementById('result-section');
const modal         = document.getElementById('processing-modal');
const modalBar      = document.getElementById('modal-bar');

const STEPS = [
  { id: 'step-1', label: 'Analizando el vídeo',       pct: 15,  ms: 800  },
  { id: 'step-2', label: 'Extrayendo transcripción',   pct: 45,  ms: 4000 },
  { id: 'step-3', label: 'Adaptando a tu perfil',      pct: 75,  ms: 8000 },
  { id: 'step-4', label: 'Generando guión',            pct: 92,  ms: 3000 },
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

    fillResult(data);
    updateQuota(data);
    resultSection.classList.remove('hidden');
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch (err) {
    closeModal();
    showError('Error de conexión. Comprueba tu internet e inténtalo de nuevo.');
  }
}

/* ── Modal ──────────────────────────────── */
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
  modalBar.style.width = '0%';
  STEPS.forEach(s => {
    const el  = document.getElementById(s.id);
    const dot = el.querySelector('.step-dot');
    el.classList.remove('live', 'done');
    dot.classList.remove('active', 'done');
  });
}

function animateSteps() {
  let elapsed = 0;
  STEPS.forEach((step, i) => {
    const t = setTimeout(() => {
      // Marca el anterior como hecho
      if (i > 0) {
        const prev    = document.getElementById(STEPS[i - 1].id);
        const prevDot = prev.querySelector('.step-dot');
        prev.classList.remove('live');
        prev.classList.add('done');
        prevDot.classList.remove('active');
        prevDot.classList.add('done');
      }
      // Activa el actual
      const el  = document.getElementById(step.id);
      const dot = el.querySelector('.step-dot');
      el.classList.add('live');
      dot.classList.add('active');
      modalBar.style.width = step.pct + '%';
    }, elapsed);
    stepTimers.push(t);
    elapsed += step.ms;
  });
}

/* ── Fill result ────────────────────────── */
function fillResult(data) {
  setText('hook-text',    data.hook       || '');
  setText('dev-text',     data.desarrollo || '');
  setText('conc-text',    data.conclusion || '');
  setText('caption-text', data.caption    || '');
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function updateQuota(data) {
  const badge = document.querySelector('.quota-badge');
  if (!badge || data.limit === null || data.limit === undefined) return;
  const numEl = badge.querySelector('.quota-number');
  if (numEl && data.remaining !== null && data.remaining !== undefined) {
    numEl.textContent = data.remaining;
    badge.classList.remove('quota-low', 'quota-empty');
    if (data.remaining === 0) {
      badge.classList.add('quota-empty');
      generateBtn.disabled = true;
    } else if (data.remaining <= 5) {
      badge.classList.add('quota-low');
    }
  }
}

/* ── Error ──────────────────────────────── */
function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove('hidden');
  errorBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function hideError() { errorBox.classList.add('hidden'); }

/* ── Copy buttons ─────────────────────── */
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
