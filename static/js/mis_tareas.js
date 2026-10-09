/* Panel de tareas de una colaboradora.
 *
 * Tres gestos y nada más: marcar, anotar y apuntar. Todo se guarda solo, sin
 * botón de guardar y sin recargar.
 *
 * Dos decisiones que conviene no deshacer:
 *
 *  · Se pinta primero y se pregunta después (marcado optimista). Con una mala
 *    cobertura, esperar la respuesta del servidor para que el círculo se ponga
 *    verde hace que la página parezca rota y se acabe tocando dos veces.
 *  · Si el servidor dice que no, se deshace y se avisa. Nunca se deja la
 *    pantalla diciendo una cosa y la base de datos otra, que es peor que un
 *    error: es un error invisible.
 */
(() => {
  'use strict';

  const envoltorio = document.querySelector('.envoltorio');
  if (!envoltorio) return;

  const listas = {
    fijas:     document.getElementById('fijas'),
    puntuales: document.getElementById('puntuales'),
    hechas:    document.getElementById('hechas'),
  };

  // ── Contadores ──────────────────────────────────────────────────────────
  function recontar() {
    let pendientes = 0;
    for (const [clave, ul] of Object.entries(listas)) {
      const n = ul.children.length;
      const marca = document.querySelector(`[data-cuenta="${clave}"]`);
      if (marca) marca.textContent = n;
      const vacio = document.querySelector(`[data-vacio="${clave}"]`);
      if (vacio) vacio.hidden = n > 0;
      if (clave !== 'hechas') pendientes += n;
    }
    const num = document.getElementById('cuenta-pendientes');
    const palabra = document.getElementById('cuenta-palabra');
    if (num) num.textContent = pendientes;
    if (palabra) palabra.textContent = pendientes === 1 ? 'cosa pendiente' : 'cosas pendientes';
  }

  // ── Marcar / desmarcar ──────────────────────────────────────────────────
  async function alternar(li) {
    if (li.dataset.ocupada) return;        // doble toque en un móvil lento
    li.dataset.ocupada = '1';

    const estabaHecha = li.classList.contains('--hecha');
    const origen = li.parentElement;
    const hermano = li.nextElementSibling;

    // Se mueve ya, antes de preguntar.
    li.classList.toggle('--hecha', !estabaHecha);
    (estabaHecha ? (li.dataset.fija === '1' ? listas.fijas : listas.puntuales)
                 : listas.hechas).prepend(li);
    recontar();

    try {
      const r = await fetch(`/mis-tareas/${li.dataset.id}/estado`, { method: 'POST' });
      if (!r.ok) throw new Error(r.status === 401 ? 'sesion' : 'fallo');
      const t = await r.json();

      li.dataset.fija = t.fija ? '1' : '0';
      li.classList.toggle('--hecha', t.estado === 'hecha');
      // El servidor dice en qué grupo va. Normalmente ya está ahí, pero una
      // fija de una semana vieja vuelve a «Puntuales» y no a «De cada semana».
      const destino = listas[t.bloque];
      if (destino && li.parentElement !== destino) destino.prepend(li);
      const marcas = li.querySelector('.marcas');
      if (marcas) {
        marcas.innerHTML = t.estado === 'hecha' ? chipsHecha(t) : chipsPendiente(t);
      }
      const boton = li.querySelector('[data-marcar]');
      if (boton) {
        boton.setAttribute('aria-pressed', t.estado === 'hecha' ? 'true' : 'false');
        boton.setAttribute('aria-label',
          t.estado === 'hecha' ? 'Desmarcar' : 'Marcar como hecha');
      }
    } catch (e) {
      // Se deshace el movimiento: la pantalla vuelve a lo que de verdad hay.
      li.classList.toggle('--hecha', estabaHecha);
      if (hermano) origen.insertBefore(li, hermano); else origen.appendChild(li);
      avisar(e.message === 'sesion'
        ? 'Se cerró la sesión. Recarga y vuelve a entrar.'
        : 'No se pudo guardar. Mira si tienes conexión.');
    } finally {
      delete li.dataset.ocupada;
      recontar();
    }
  }

  // El día del que era la tarea, no sólo cuándo se marcó: una diaria deja
  // varias filas iguales en la semana y sin el día no se distinguen.
  function chipsHecha(t) {
    if (t.dia) return `<span class="chip">${t.dia} ${t.fecha_corta}</span>` +
                      '<span class="chip --ok">Hecha</span>';
    return `<span class="chip --ok">Hecha${t.hecha_el ? ' el ' + t.hecha_el : ''}</span>`;
  }

  function chipsPendiente(t) {
    const trozos = [];
    if (t.urgente) trozos.push('<span class="chip --urge">Urgente</span>');
    if (t.vencida) trozos.push(`<span class="chip --tarde">Se pasó el ${t.fecha_corta}</span>`);
    else if (t.hoy) trozos.push('<span class="chip --hoy">Hoy</span>');
    else if (t.dia) trozos.push(`<span class="chip">${t.dia} ${t.fecha_corta}</span>`);
    return trozos.join('');
  }

  // ── Anotaciones ─────────────────────────────────────────────────────────
  const esperas = new WeakMap();

  function decir(li, texto, mal) {
    const caja = li.querySelector('[data-estado]');
    if (!caja) return;
    caja.querySelector('span').textContent = texto;
    caja.classList.toggle('--mal', !!mal);
    caja.classList.toggle('--visible', !!texto);
  }

  async function guardarNota(li) {
    const area = li.querySelector('[data-texto]');
    if (!area) return;
    const cuerpo = new URLSearchParams({ valor: area.value });
    decir(li, 'Guardando…');
    try {
      const r = await fetch(`/mis-tareas/${li.dataset.id}/nota`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: cuerpo,
      });
      if (!r.ok) throw new Error(r.status === 401 ? 'sesion' : 'fallo');
      decir(li, 'Guardado');

      // La nota de debajo tiene que decir lo mismo que la caja de arriba.
      let vista = li.querySelector('.nota-vista');
      const limpio = area.value.trim();
      if (limpio && !vista) {
        vista = document.createElement('div');
        vista.className = 'nota-vista';
        li.querySelector('.nota-caja').before(vista);
      }
      if (vista) {
        if (limpio) vista.textContent = limpio; else vista.remove();
      }
      const abrir = li.querySelector('[data-nota]');
      if (abrir) abrir.textContent = limpio ? 'Ver o cambiar la nota' : 'Añadir una nota';
    } catch (e) {
      decir(li, e.message === 'sesion' ? 'Se cerró la sesión, recarga' : 'No se guardó', true);
    }
  }

  // ── Un solo oyente para toda la lista ───────────────────────────────────
  envoltorio.addEventListener('click', (ev) => {
    const marcar = ev.target.closest('[data-marcar]');
    if (marcar) { alternar(marcar.closest('.tarea')); return; }

    const abrir = ev.target.closest('[data-nota]');
    if (abrir) {
      const li = abrir.closest('.tarea');
      const seAbre = !li.classList.contains('--abierta');
      li.classList.toggle('--abierta', seAbre);
      if (seAbre) {
        const area = li.querySelector('[data-texto]');
        area.focus();
        // El cursor al final, no al principio del texto que ya hay.
        area.setSelectionRange(area.value.length, area.value.length);
      } else {
        decir(li, '');
      }
    }
  });

  envoltorio.addEventListener('input', (ev) => {
    const area = ev.target.closest('[data-texto]');
    if (!area) return;
    const li = area.closest('.tarea');
    clearTimeout(esperas.get(li));
    // Se espera a que deje de escribir: un guardado por tecla sería una
    // petición por letra, y con mala cobertura llegarían desordenadas.
    esperas.set(li, setTimeout(() => guardarNota(li), 700));
  });

  // Si cierra el móvil o cambia de pestaña, lo escrito no se pierde.
  envoltorio.addEventListener('focusout', (ev) => {
    const area = ev.target.closest('[data-texto]');
    if (!area) return;
    const li = area.closest('.tarea');
    clearTimeout(esperas.get(li));
    guardarNota(li);
  });

  // ── Apuntar una nueva ───────────────────────────────────────────────────
  const form = document.getElementById('apuntar');
  form?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const campo = form.querySelector('input');
    const boton = form.querySelector('button');
    const texto = campo.value.trim();
    if (!texto) return;

    boton.disabled = true;
    try {
      const r = await fetch('/mis-tareas/nueva', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ texto }),
      });
      if (!r.ok) throw new Error(r.status === 401 ? 'sesion' : 'fallo');
      const { html } = await r.json();
      listas.puntuales.insertAdjacentHTML('beforeend', html);
      campo.value = '';
      // El campo se queda enfocado para poder apuntar varias seguidas.
      campo.focus();
      recontar();
    } catch (e) {
      avisar(e.message === 'sesion'
        ? 'Se cerró la sesión. Recarga y vuelve a entrar.'
        : 'No se pudo añadir. Mira si tienes conexión.');
    } finally {
      boton.disabled = false;
    }
  });

  function avisar(texto) { window.alert(texto); }
})();
