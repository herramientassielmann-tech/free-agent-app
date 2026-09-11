/* Gestor de tareas del equipo.
 *
 * Todo gira alrededor de la barra de captura: escribir una línea y pulsar
 * Enter. Los gestores que mejor funcionan coinciden en que la diferencia entre
 * escribir una frase y pasar por cuatro menús es la diferencia entre un sistema
 * que se usa y uno que se abandona. Por eso el campo se queda enfocado y vacío
 * después de guardar: para poder apuntar cuatro cosas seguidas sin tocar nada.
 *
 * El HTML de cada fila lo monta el servidor, no este fichero. Pintarla aquí
 * significaría tener dos versiones del mismo trozo —la de Jinja y la de JS— y
 * que se separen con el tiempo sin que nadie lo note.
 */
(function () {
  const campo = document.getElementById("eq-nueva");
  const listas = document.getElementById("eq-listas");
  if (!campo || !listas) return;

  const $ = id => document.getElementById(id);

  async function pedir(url, opciones) {
    const res = await fetch(url, opciones);
    if (!res.ok) {
      let msg = "No se pudo guardar.";
      try { msg = (await res.json()).detail || msg; } catch (e) {}
      throw new Error(msg);
    }
    return res.status === 204 ? null : res.json();
  }

  function fallo(el, msg) {
    el.classList.add("eq-fallo");
    setTimeout(() => el.classList.remove("eq-fallo"), 1600);
    if (msg) console.warn(msg);
  }

  /* Los contadores de cada bloque y el bloque vacío se recalculan a partir del
     DOM: así no hay una cuenta paralela que pueda desajustarse. */
  function recontar() {
    listas.querySelectorAll(".eq-bloque").forEach(b => {
      const n = b.querySelectorAll(".eq-fila").length;
      b.querySelector(".eq-titulo span").textContent = n;
      b.hidden = n === 0;
    });
    const vacio = $("eq-vacio");
    if (vacio) vacio.hidden = listas.querySelectorAll(".eq-fila").length > 0;
  }

  /* ── Captura ───────────────────────────────── */
  async function apuntar() {
    const texto = campo.value.trim();
    if (!texto) return;
    campo.disabled = true;
    try {
      const r = await pedir("/admin/tareas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto }),
      });
      const bloque = listas.querySelector(`[data-bloque="${r.bloque}"]`);
      bloque.querySelector(".eq-lista").insertAdjacentHTML("beforeend", r.html);
      bloque.hidden = false;
      const nueva = bloque.querySelector(".eq-fila:last-child");
      nueva.classList.add("eq-recien");
      setTimeout(() => nueva.classList.remove("eq-recien"), 900);
      campo.value = "";
      recontar();
    } catch (e) {
      fallo(campo, e.message);
    } finally {
      campo.disabled = false;
      campo.focus();          // listo para la siguiente sin tocar nada
    }
  }

  campo.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); apuntar(); }
  });
  $("eq-anadir").addEventListener("click", apuntar);

  /* ── Acciones sobre una fila ───────────────── */
  document.addEventListener("click", async e => {
    const fila = e.target.closest(".eq-fila");
    if (!fila) return;
    const id = fila.dataset.id;

    if (e.target.closest(".eq-texto")) {
      abrirPanel(fila);
      return;
    }

    if (e.target.closest(".eq-check")) {
      try {
        await pedir(`/admin/tareas/${id}/estado`, { method: "POST" });
        /* Se va de la lista con una transición corta. No se recoloca en «lo que
           llevamos hecho» al vuelo: esa parte es para repasar, no para verla
           moverse, y aparecerá en su semana la próxima vez que se entre. */
        fila.classList.add("eq-saliendo");
        setTimeout(() => { fila.remove(); recontar(); }, 260);
      } catch (err) { fallo(fila, err.message); }
      return;
    }

    const persona = e.target.closest(".eq-persona");
    if (persona && persona.tagName === "BUTTON") {
      // Pulsar el que ya está puesto lo quita: no hace falta un botón aparte
      // para desasignar.
      const ya = persona.classList.contains("eq-persona--on");
      const valor = ya ? "" : persona.dataset.quien;
      const previos = [...fila.querySelectorAll(".eq-persona--on")];
      fila.querySelectorAll(".eq-persona").forEach(b => b.classList.remove("eq-persona--on"));
      if (!ya) persona.classList.add("eq-persona--on");
      try {
        await pedir(`/admin/tareas/${id}`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ campo: "asignado_a", valor }),
        });
        fila.classList.add("eq-guardado");
        setTimeout(() => fila.classList.remove("eq-guardado"), 600);
      } catch (err) {
        // Se deshace lo pintado: si no, la pantalla diría algo que no está guardado
        fila.querySelectorAll(".eq-persona").forEach(b => b.classList.remove("eq-persona--on"));
        previos.forEach(b => b.classList.add("eq-persona--on"));
        fallo(persona, err.message);
      }
      return;
    }

    if (e.target.closest(".eq-borrar")) {
      if (!confirm("¿Borrar esta tarea?")) return;
      try {
        await pedir(`/admin/tareas/${id}`, { method: "DELETE" });
        fila.classList.add("eq-saliendo");
        setTimeout(() => { fila.remove(); recontar(); }, 260);
      } catch (err) { fallo(fila, err.message); }
    }
  });

  /* ── El panel de la tarea ──────────────────
   *
   * Se abre al pulsar el texto. Todo lo de dentro se guarda al salir del campo,
   * sin botón: es una nota rápida, no un formulario.
   */
  const panel = $("eq-panel"), fondo = $("eq-fondo");
  const pTexto = $("eq-panel-texto"), pFecha = $("eq-panel-fecha");
  const pVista = $("eq-nota-vista"), pEditar = $("eq-nota-editar");
  let abierta = null;          // la fila abierta ahora mismo

  const escapar = t => t.replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* Los enlaces se vuelven pulsables al dejar de escribir, como en las notas
     del móvil. Se escapa ANTES de enlazar: el texto lo escribe una persona y
     nunca debe llegar al HTML tal cual. */
  function conEnlaces(texto) {
    if (!texto.trim()) return '<span class="eq-nota-vacia">Escribe lo que haga falta recordar…</span>';
    return escapar(texto).replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener">$1</a>');
  }

  function pintarPanel(datos) {
    pTexto.value = datos.texto;
    pFecha.value = datos.fecha_limite || "";
    pEditar.value = datos.notas || "";
    pVista.innerHTML = conEnlaces(datos.notas || "");
    panel.querySelectorAll("#eq-panel-personas .eq-persona").forEach(b =>
      b.classList.toggle("eq-persona--on", b.dataset.quien === datos.asignado_a));
    panel.querySelectorAll(".eq-prio").forEach(b =>
      b.classList.toggle("eq-prio--on", b.dataset.prio === datos.prioridad));
  }

  function abrirPanel(fila) {
    abierta = fila;
    pintarPanel({
      texto: fila.querySelector(".eq-texto").childNodes[0].textContent.trim(),
      fecha_limite: fila.querySelector(".eq-dia")?.value || "",
      notas: fila.dataset.notas || "",
      asignado_a: fila.dataset.quien || null,
      prioridad: fila.dataset.prioridad || "normal",
    });
    panel.hidden = fondo.hidden = false;
    requestAnimationFrame(() => panel.classList.add("eq-panel--abierto"));
  }

  function cerrarPanel() {
    panel.classList.remove("eq-panel--abierto");
    setTimeout(() => { panel.hidden = fondo.hidden = true; }, 220);
    abierta = null;
  }

  async function guardarCampo(campo, valor) {
    if (!abierta) return null;
    return pedir(`/admin/tareas/${abierta.dataset.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ campo, valor }),
    });
  }

  $("eq-cerrar").addEventListener("click", cerrarPanel);
  fondo.addEventListener("click", cerrarPanel);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !panel.hidden) cerrarPanel();
  });

  // La nota: mirar -> escribir -> guardar al salir
  pVista.addEventListener("click", () => {
    pVista.hidden = true; pEditar.hidden = false; pEditar.focus();
    pEditar.setSelectionRange(pEditar.value.length, pEditar.value.length);
  });
  pEditar.addEventListener("blur", async () => {
    const texto = pEditar.value;
    pEditar.hidden = true; pVista.hidden = false;
    pVista.innerHTML = conEnlaces(texto);
    try {
      await guardarCampo("notas", texto);
      if (abierta) {
        abierta.dataset.notas = texto;
        const marca = abierta.querySelector(".eq-tiene-nota");
        if (texto.trim() && !marca) {
          abierta.querySelector(".eq-texto").insertAdjacentHTML("beforeend",
            '<span class="eq-tiene-nota" title="Tiene notas">≡</span>');
        } else if (!texto.trim() && marca) { marca.remove(); }
      }
    } catch (err) { fallo(pVista, err.message); }
  });

  pTexto.addEventListener("blur", async () => {
    const nuevo = pTexto.value.trim();
    if (!nuevo || !abierta) return;
    try {
      await guardarCampo("texto", nuevo);
      abierta.querySelector(".eq-texto").childNodes[0].textContent = nuevo;
    } catch (err) { fallo(pTexto, err.message); }
  });

  pFecha.addEventListener("change", async () => {
    try {
      await guardarCampo("fecha_limite", pFecha.value);
      const enFila = abierta?.querySelector(".eq-dia");
      if (enFila) enFila.value = pFecha.value;
    } catch (err) { fallo(pFecha, err.message); }
  });

  panel.addEventListener("click", async e => {
    const persona = e.target.closest("#eq-panel-personas .eq-persona");
    if (persona) {
      const ya = persona.classList.contains("eq-persona--on");
      const valor = ya ? "" : persona.dataset.quien;
      panel.querySelectorAll("#eq-panel-personas .eq-persona")
           .forEach(b => b.classList.remove("eq-persona--on"));
      if (!ya) persona.classList.add("eq-persona--on");
      try {
        await guardarCampo("asignado_a", valor);
        if (abierta) {
          abierta.dataset.quien = valor;
          const sel = abierta.querySelector(".eq-sel--quien");
          if (sel) sel.value = valor;
        }
      } catch (err) { fallo(persona, err.message); }
      return;
    }
    const prio = e.target.closest(".eq-prio");
    if (prio) {
      panel.querySelectorAll(".eq-prio").forEach(b => b.classList.remove("eq-prio--on"));
      prio.classList.add("eq-prio--on");
      try {
        await guardarCampo("prioridad", prio.dataset.prio);
        if (abierta) {
          abierta.dataset.prioridad = prio.dataset.prio;
          const sel = abierta.querySelector(".eq-sel--prio");
          if (sel) sel.value = prio.dataset.prio;
        }
      } catch (err) { fallo(prio, err.message); }
    }
  });

  $("eq-panel-borrar").addEventListener("click", async () => {
    if (!abierta || !confirm("¿Borrar esta tarea?")) return;
    const fila = abierta;
    try {
      await pedir(`/admin/tareas/${fila.dataset.id}`, { method: "DELETE" });
      cerrarPanel();
      fila.classList.add("eq-saliendo");
      setTimeout(() => { fila.remove(); recontar(); }, 260);
    } catch (err) { fallo(panel, err.message); }
  });

  /* La fecha se guarda al cambiarla, sin botón de guardar. */
  document.addEventListener("change", async e => {
    const control = e.target.closest("[data-campo]");
    if (!control) return;
    const fila = control.closest(".eq-fila");
    if (!fila) return;
    try {
      await pedir(`/admin/tareas/${fila.dataset.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ campo: control.dataset.campo, valor: control.value }),
      });
      // El color de la fila cuelga de estos dos atributos, así que el cambio se
      // ve en el momento sin recargar nada.
      if (control.dataset.campo === "asignado_a") fila.dataset.quien = control.value;
      if (control.dataset.campo === "prioridad") fila.dataset.prioridad = control.value;
      fila.classList.add("eq-guardado");
      setTimeout(() => fila.classList.remove("eq-guardado"), 600);
    } catch (err) { fallo(control, err.message); }
  });
})();
