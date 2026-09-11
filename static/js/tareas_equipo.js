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
      fila.classList.add("eq-guardado");
      setTimeout(() => fila.classList.remove("eq-guardado"), 600);
    } catch (err) { fallo(control, err.message); }
  });
})();
