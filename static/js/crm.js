/* CRM de leads — tablero de tarjetas.
 *
 * Todo lo que hace falta para que un realtor lo use de verdad: arrastrar una
 * tarjeta, apuntar una línea de lo hablado, y ver a quién lleva días sin tocar.
 * Nada más, a propósito.
 */
(function () {
  const tablero = document.getElementById("crm-tablero");
  if (!tablero) return;

  const panel   = document.getElementById("crm-panel");
  const fondo   = document.getElementById("crm-fondo");
  const modal   = document.getElementById("crm-modal");
  let abierto   = null;   // id del lead en el panel
  let editando  = null;   // id si el formulario edita en vez de crear

  const $ = id => document.getElementById(id);

  async function api(url, opciones = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opciones,
    });
    if (!res.ok) {
      let msg = "Algo ha fallado. Inténtalo otra vez.";
      try { msg = (await res.json()).detail || msg; } catch (e) {}
      throw new Error(msg);
    }
    return res.status === 204 ? null : res.json();
  }

  /* ── Tarjetas ─────────────────────────────── */
  function pintarTarjeta(l) {
    const art = document.createElement("article");
    art.className = `crm-tarjeta crm-urg--${l.urgencia}`;
    art.dataset.id = l.id;
    const trozos = [`<b class="crm-nombre"></b>`];
    if (l.interes) trozos.push(`<span class="crm-interes"></span>`);
    // El seguimiento vive en el panel, no aquí: el tablero se lee de un vistazo
    // y una fecha por tarjeta lo convierte en una hoja de cálculo.
    if (l.origen || l.presupuesto || l.tareas_pendientes) {
      trozos.push(`<div class="crm-pie">
        ${l.origen ? '<span class="crm-origen"></span>' : ""}
        ${l.presupuesto ? '<span class="crm-presupuesto"></span>' : ""}
        ${l.tareas_pendientes ? `<span class="crm-tareas ${l.tareas_vencidas ? "crm-tareas--vencida" : ""}">${l.tareas_vencidas ? "⚠ " : "☑ "}${l.tareas_pendientes}</span>` : ""}</div>`);
    }
    art.innerHTML = trozos.join("");
    // textContent, no innerHTML: el nombre lo escribe el usuario
    art.querySelector(".crm-nombre").textContent = l.nombre;
    if (l.interes) art.querySelector(".crm-interes").textContent = l.interes;
    if (l.origen) art.querySelector(".crm-origen").textContent = l.origen;
    if (l.presupuesto) art.querySelector(".crm-presupuesto").textContent = l.presupuesto;
    return art;
  }

  function actualizarTarjeta(l) {
    const vieja = tablero.querySelector(`.crm-tarjeta[data-id="${l.id}"]`);
    const nueva = pintarTarjeta(l);
    if (vieja) {
      vieja.replaceWith(nueva);
    } else {
      tablero.querySelector(`[data-lista="${l.etapa}"]`)?.prepend(nueva);
    }
    contar();
  }

  function pintarMeta(lead) {
    const hablado = lead.dias === 0
      ? "✓ Hablasteis hoy"
      : `✓ Hablasteis el ${lead.contacto_fecha} · hace ${lead.dias} día${lead.dias === 1 ? "" : "s"}`;
    const meta = $("crm-panel-meta");
    meta.textContent = [lead.origen, lead.contacto, hablado].filter(Boolean).join(" · ");
    meta.className = "crm-meta-visto crm-meta-visto--" + lead.urgencia;
  }

  /* ── Seguimiento: la cadena de veces que has hablado ───────── */

  const REDUCIR = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function pintarTick(c) {
    const d = document.createElement("div");
    d.className = "crm-tick";
    d.title = "Hablasteis el " + c.completa;
    const i = document.createElement("span");
    i.className = "crm-tick-icono"; i.textContent = "✓";
    const f = document.createElement("span");
    f.className = "crm-tick-fecha"; f.textContent = c.fecha;
    d.append(i, f);
    return d;
  }

  function pintarCuenta(n) {
    $("crm-seguimiento-cuenta").textContent =
      n ? `${n} contacto${n === 1 ? "" : "s"}` : "";
  }

  /* Llegan del servidor del más reciente al más antiguo, que es el orden en
   * que se pintan: el último arriba y el primero abajo. */
  function pintarSeguimiento(contactos) {
    const cont = $("crm-seguimiento");
    cont.innerHTML = "";
    pintarCuenta(contactos.length);
    if (!contactos.length) {
      const p = document.createElement("p");
      p.className = "crm-sin-notas";
      p.textContent = "Aún no has marcado ningún contacto.";
      cont.appendChild(p);
      return;
    }
    contactos.forEach(c => cont.appendChild(pintarTick(c)));
  }

  /* La bolita verde que cae del botón a la lista y se vuelve el tick.
   *
   * El recorrido no es adorno: enseña de dónde sale el tick y dónde se queda,
   * que es lo que hace entender la lista sin tener que leer nada. Se estira al
   * caer y se achata al llegar, que es lo que la hace parecer líquida en vez
   * de un círculo que se desplaza. */
  async function animarContacto(contacto, contactos) {
    const boton = $("crm-contactado");
    const lista = $("crm-seguimiento");
    const previos = contactos.filter(c => c.id !== contacto.id);

    if (REDUCIR || !boton || !lista) { pintarSeguimiento(contactos); return; }

    // Si el destino está fuera de pantalla la bolita caería a ninguna parte.
    lista.scrollIntoView({ behavior: "smooth", block: "center" });
    await new Promise(r => setTimeout(r, 340));

    pintarSeguimiento(previos);   // la lista sin el nuevo: aterriza sobre ella
    pintarCuenta(contactos.length);

    const rb = boton.getBoundingClientRect();
    const rl = lista.getBoundingClientRect();
    const D = 15;
    const y0 = rb.top + rb.height / 2 - D / 2;
    const caida = Math.max(rl.top + 9 - y0, 28);

    const bolita = document.createElement("div");
    bolita.className = "crm-bolita";
    bolita.style.left = (rb.left + rb.width / 2 - D / 2) + "px";
    bolita.style.top = y0 + "px";
    document.body.appendChild(bolita);

    await bolita.animate([
      { transform: "translateY(0) scale(1,1)", offset: 0 },
      { transform: `translateY(${caida * .45}px) scale(.80,1.32)`, offset: .42 },
      { transform: `translateY(${caida}px) scale(1.38,.66)`, offset: .78 },
      { transform: `translateY(${caida}px) scale(1,1)`, offset: .90 },
      { transform: `translateY(${caida}px) scale(.2,.2)`, opacity: 0, offset: 1 },
    ], { duration: 720, easing: "cubic-bezier(.35,.02,.28,1)", fill: "forwards" }).finished;

    bolita.remove();
    lista.querySelector(".crm-sin-notas")?.remove();
    const el = pintarTick(contacto);
    el.classList.add("crm-tick--nuevo");
    lista.prepend(el);
  }

  /* Quita a alguien del aviso de «llevas días sin hablar con…».
   * Sin esto el aviso seguiría nombrando a quien acabas de llamar hasta
   * recargar la página, que es justo cuando deja de tener sentido: pierdes
   * la confianza en el aviso y acabas ignorándolo. */
  function quitarDeOlvidados(id) {
    const btn = document.querySelector(`.crm-olvidado[data-id="${id}"]`);
    if (!btn) return;
    btn.remove();
    const caja = document.querySelector(".crm-olvidados");
    if (caja && !caja.querySelector(".crm-olvidado")) caja.remove();
  }

  function contar() {
    tablero.querySelectorAll("[data-lista]").forEach(lista => {
      const c = document.querySelector(`[data-cuenta="${lista.dataset.lista}"]`);
      if (c) c.textContent = lista.children.length;
    });
  }

  /* ── Arrastrar entre etapas ───────────────── */
  tablero.querySelectorAll("[data-lista]").forEach(lista => {
    new Sortable(lista, {
      group: "leads",
      animation: 150,
      ghostClass: "crm-fantasma",
      dragClass: "crm-arrastrando",
      // En móvil hay que mantener pulsado, si no el scroll del tablero
      // se convertiría en arrastres accidentales
      delay: 120,
      delayOnTouchOnly: true,
      touchStartThreshold: 5,
      // Sin esto el tablero no se mueve al arrastrar hacia un lado, y las
      // columnas que quedan fuera de pantalla son inalcanzables.
      scroll: tablero,
      scrollSensitivity: 110,
      scrollSpeed: 22,
      bubbleScroll: true,
      forceAutoScrollFallback: true,
      onEnd: async (ev) => {
        const id = ev.item.dataset.id;
        const etapa = ev.to.dataset.lista;
        contar();
        try {
          const { lead } = await api(`/crm/leads/${id}/mover`, {
            method: "POST",
            body: JSON.stringify({ etapa, posicion: ev.newIndex }),
          });
          // La urgencia cambia al pasar a "frío": se repinta
          ev.item.className = `crm-tarjeta crm-urg--${lead.urgencia}`;
        } catch (e) {
          alert(e.message);
          ev.from.insertBefore(ev.item, ev.from.children[ev.oldIndex] || null);
          contar();
        }
      },
    });
  });

  /* ── Panel del lead ───────────────────────── */
  function cerrarPanel() {
    panel.hidden = true; fondo.hidden = true; abierto = null;
  }

  async function abrirPanel(id) {
    try {
      const { lead, notas, tareas, contactos } = await api(`/crm/leads/${id}`);
      abierto = id;
      $("crm-panel-nombre").textContent = lead.nombre;
      pintarMeta(lead);

      const wa = $("crm-wa");
      if (lead.telefono) {
        wa.href = "https://wa.me/" + lead.telefono.replace(/[^0-9]/g, "");
        wa.hidden = false;
      } else { wa.hidden = true; }

      const datos = $("crm-panel-datos");
      datos.innerHTML = "";
      [["Busca", lead.interes], ["Presupuesto", lead.presupuesto],
       ["Contacto", lead.contacto], ["Teléfono", lead.telefono]]
        .filter(([, v]) => v)
        .forEach(([k, v]) => {
          const fila = document.createElement("div");
          fila.className = "crm-dato";
          const b = document.createElement("b"); b.textContent = k;
          const s = document.createElement("span"); s.textContent = v;
          fila.append(b, s); datos.appendChild(fila);
        });

      const cont = $("crm-notas");
      cont.innerHTML = "";
      if (!notas.length) {
        const p = document.createElement("p");
        p.className = "crm-sin-notas";
        p.textContent = "Todavía no has apuntado nada.";
        cont.appendChild(p);
      }
      notas.forEach(n => {
        const d = document.createElement("div");
        d.className = "crm-nota";
        const t = document.createElement("p"); t.textContent = n.texto;
        const f = document.createElement("time"); f.textContent = n.fecha;
        d.append(t, f); cont.appendChild(d);
      });

      pintarTareas(tareas);
      pintarSeguimiento(contactos || []);
      panel.hidden = false; fondo.hidden = false;
    } catch (e) { alert(e.message); }
  }

  function pintarTareas(tareas) {
    const cont = $("crm-tareas-lista");
    cont.innerHTML = "";
    if (!tareas.length) {
      const p = document.createElement("p");
      p.className = "crm-sin-notas";
      p.textContent = "Sin tareas. Añade lo próximo que tengas que hacer.";
      cont.appendChild(p);
      return;
    }
    tareas.forEach(t => {
      const fila = document.createElement("div");
      fila.className = "crm-tarea" + (t.hecha ? " crm-tarea--hecha" : "")
                     + (t.vencida ? " crm-tarea--vencida" : "")
                     + (t.hoy ? " crm-tarea--hoy" : "");

      const check = document.createElement("button");
      check.type = "button";
      check.className = "crm-tarea-check" + (t.hecha ? " crm-tarea-check--on" : "");
      check.textContent = t.hecha ? "✓" : "";
      check.setAttribute("aria-label", t.hecha ? "Desmarcar" : "Marcar como hecha");
      check.addEventListener("click", async () => {
        check.disabled = true;
        try {
          const r = await api(`/crm/tareas/${t.id}/toggle`, { method: "POST" });
          actualizarTarjeta(r.lead);
          abrirPanel(abierto);
        } catch (e) { alert(e.message); check.disabled = false; }
      });

      const txt = document.createElement("span");
      txt.className = "crm-tarea-texto";
      txt.textContent = t.texto;

      const meta = document.createElement("span");
      meta.className = "crm-tarea-fecha";
      if (t.hecha) meta.textContent = t.completada_en ? "Hecha el " + t.completada_en : "Hecha";
      else if (t.vencida) meta.textContent = "Venció el " + fechaCorta(t.fecha_limite);
      else if (t.hoy) meta.textContent = "Es hoy";
      else if (t.fecha_limite) meta.textContent = fechaCorta(t.fecha_limite);

      const borrar = document.createElement("button");
      borrar.type = "button"; borrar.className = "crm-tarea-x";
      borrar.textContent = "×"; borrar.setAttribute("aria-label", "Eliminar tarea");
      borrar.addEventListener("click", async () => {
        try {
          await api(`/crm/tareas/${t.id}`, { method: "DELETE" });
          abrirPanel(abierto);
        } catch (e) { alert(e.message); }
      });

      fila.append(check, txt, meta, borrar);
      cont.appendChild(fila);
    });
  }

  function fechaCorta(iso) {
    if (!iso) return "";
    const [a, m, d] = iso.split("-");
    return `${d}/${m}`;
  }

  async function anadirTarea() {
    const texto = $("crm-tarea-texto").value.trim();
    if (!texto || !abierto) return;
    try {
      const r = await api(`/crm/leads/${abierto}/tareas`, {
        method: "POST",
        body: JSON.stringify({ texto, fecha_limite: $("crm-tarea-fecha").value || null }),
      });
      $("crm-tarea-texto").value = ""; $("crm-tarea-fecha").value = "";
      actualizarTarjeta(r.lead);
      abrirPanel(abierto);
    } catch (e) { alert(e.message); }
  }
  $("crm-tarea-add").addEventListener("click", anadirTarea);
  $("crm-tarea-texto").addEventListener("keydown", e => {
    if (e.key === "Enter") anadirTarea();
  });

  tablero.addEventListener("click", e => {
    const t = e.target.closest(".crm-tarjeta");
    if (t) abrirPanel(t.dataset.id);
  });
  document.querySelectorAll(".crm-olvidado").forEach(b =>
    b.addEventListener("click", () => abrirPanel(b.dataset.id)));
  $("crm-cerrar").addEventListener("click", cerrarPanel);
  fondo.addEventListener("click", cerrarPanel);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !panel.hidden) cerrarPanel();
  });

  /* ── Apuntar lo hablado ───────────────────── */
  async function apuntar() {
    const texto = $("crm-nota").value.trim();
    if (!texto || !abierto) return;
    try {
      const { lead } = await api(`/crm/leads/${abierto}/notas`, {
        method: "POST", body: JSON.stringify({ texto }),
      });
      $("crm-nota").value = "";
      actualizarTarjeta(lead);
      quitarDeOlvidados(lead.id);   // apuntar algo también es haber hablado
      abrirPanel(abierto);
    } catch (e) { alert(e.message); }
  }
  $("crm-guardar-nota").addEventListener("click", apuntar);
  $("crm-nota").addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") apuntar();
  });

  $("crm-contactado").addEventListener("click", async () => {
    if (!abierto) return;
    try {
      const { lead, contacto, contactos } =
        await api(`/crm/leads/${abierto}/contactado`, { method: "POST" });
      actualizarTarjeta(lead);
      quitarDeOlvidados(lead.id);
      pintarMeta(lead);
      // Nada de volver a abrir el panel: eso repintaría la lista y se llevaría
      // por delante la animación justo cuando el tick está aterrizando.
      await animarContacto(contacto, contactos || []);
    } catch (e) { alert(e.message); }
  });

  $("crm-borrar").addEventListener("click", async () => {
    if (!abierto) return;
    if (!confirm("Se borrará este lead y todo lo que hayas apuntado. ¿Seguro?\n\n" +
                 "Si solo ha dejado de responder, mejor muévelo a «En frío».")) return;
    try {
      await api(`/crm/leads/${abierto}`, { method: "DELETE" });
      tablero.querySelector(`.crm-tarjeta[data-id="${abierto}"]`)?.remove();
      contar(); cerrarPanel();
    } catch (e) { alert(e.message); }
  });

  /* ── Alta y edición ───────────────────────── */
  const campos = ["nombre", "origen", "telefono", "contacto", "interes", "presupuesto"];

  function abrirForm(lead) {
    editando = lead ? lead.id : null;
    $("crm-form-titulo").textContent = lead ? "Editar lead" : "Nuevo lead";
    campos.forEach(c => $("f-" + c).value = lead ? (lead[c] || "") : "");
    $("crm-form-error").classList.add("hidden");
    modal.classList.remove("hidden");
    $("f-nombre").focus();
  }
  function cerrarForm() { modal.classList.add("hidden"); editando = null; }

  $("crm-nuevo").addEventListener("click", () => abrirForm(null));
  $("crm-form-cancelar").addEventListener("click", cerrarForm);
  modal.addEventListener("click", e => { if (e.target === modal) cerrarForm(); });

  $("crm-editar").addEventListener("click", async () => {
    if (!abierto) return;
    const { lead } = await api(`/crm/leads/${abierto}`);
    cerrarPanel(); abrirForm(lead);
  });

  $("crm-form-guardar").addEventListener("click", async () => {
    const cuerpo = {};
    campos.forEach(c => cuerpo[c] = $("f-" + c).value.trim());
    if (!cuerpo.nombre) {
      const err = $("crm-form-error");
      err.textContent = "Ponle al menos un nombre.";
      err.classList.remove("hidden");
      return;
    }
    try {
      const { lead } = editando
        ? await api(`/crm/leads/${editando}`, { method: "PATCH", body: JSON.stringify(cuerpo) })
        : await api("/crm/leads", { method: "POST", body: JSON.stringify(cuerpo) });
      actualizarTarjeta(lead);
      cerrarForm();
    } catch (e) {
      const err = $("crm-form-error");
      err.textContent = e.message;
      err.classList.remove("hidden");
    }
  });
})();
