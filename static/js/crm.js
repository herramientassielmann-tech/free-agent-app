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

  const esperar = ms => new Promise(r => setTimeout(r, ms));

  /* Un aro que se expande y se apaga. Marca de dónde sale la bolita y dónde
   * aterriza, que es lo que hace que se vea el gesto entero y no solo el bicho
   * moviéndose. */
  function onda(x, y, tam) {
    const o = document.createElement("div");
    o.className = "crm-onda";
    o.style.left = (x - tam / 2) + "px";
    o.style.top = (y - tam / 2) + "px";
    o.style.width = o.style.height = tam + "px";
    document.body.appendChild(o);
    o.animate(
      [{ transform: "scale(.3)", opacity: .75 }, { transform: "scale(1)", opacity: 0 }],
      { duration: 620, easing: "cubic-bezier(.2,.7,.3,1)" }
    ).finished.then(() => o.remove());
  }

  /* La bolita va del botón hasta el hueco exacto donde va a quedarse el tick.
   *
   * Tres cosas la hacen legible y no un adorno:
   *  · El hueco se abre ANTES, así los ticks de abajo se apartan despacio en
   *    vez de dar un salto cuando aparece el nuevo.
   *  · Va en arco y con un impulso hacia arriba al salir. En línea recta parece
   *    un objeto soltado; en arco parece algo vivo que va a un sitio.
   *  · Deja estela y rompe en un aro al llegar, que es lo que se ve de verdad
   *    en una pantalla de portátil a plena luz. */
  async function animarContacto(contacto, contactos) {
    const boton = $("crm-contactado");
    const lista = $("crm-seguimiento");
    const previos = contactos.filter(c => c.id !== contacto.id);

    if (REDUCIR || !boton || !lista) { pintarSeguimiento(contactos); return; }

    pintarSeguimiento(previos);
    pintarCuenta(contactos.length);

    // Solo se espera al scroll si de verdad hace falta: si la lista ya se ve,
    // esperar es tiempo muerto mirando una pantalla quieta.
    const rl = lista.getBoundingClientRect();
    if (rl.top < 8 || rl.bottom > window.innerHeight - 8) {
      lista.scrollIntoView({ behavior: "smooth", block: "center" });
      await esperar(340);
    }

    // 1. Se prepara el hueco. Se mide un tick de verdad si lo hay, para que el
    //    destino sea exactamente el sitio que va a ocupar.
    const modelo = lista.querySelector(".crm-tick");
    const alto = modelo ? modelo.offsetHeight : 26;
    const hueco = document.createElement("div");
    hueco.className = "crm-hueco";
    lista.querySelector(".crm-sin-notas")?.remove();
    lista.prepend(hueco);

    // 2. Origen y destino reales, en los dos ejes. El hueco todavía mide cero,
    //    pero su borde de arriba ya está donde va a quedarse.
    const D = 20;
    const rb = boton.getBoundingClientRect();
    const rh = hueco.getBoundingClientRect();
    const x0 = rb.left + rb.width / 2;
    const y0 = rb.top + rb.height / 2;
    const x1 = rh.left + 13;               // donde empieza la píldora
    const y1 = rh.top + alto / 2;
    const dx = x1 - x0, dy = y1 - y0;

    // El hueco se abre MIENTRAS la bolita vuela, no antes: los de abajo se
    // apartan justo a tiempo y no hay un segundo de pantalla parada.
    const apertura = hueco.animate(
      [{ height: "0px" }, { height: alto + "px" }],
      { duration: 620, easing: "cubic-bezier(.32,.72,0,1)", fill: "forwards" }
    ).finished;

    onda(x0, y0, 54);

    const bolita = document.createElement("div");
    bolita.className = "crm-bolita";
    bolita.style.left = (x0 - D / 2) + "px";
    bolita.style.top = (y0 - D / 2) + "px";
    document.body.appendChild(bolita);

    const estela = setInterval(() => {
      const r = bolita.getBoundingClientRect();
      const g = document.createElement("div");
      g.className = "crm-estela";
      g.style.left = r.left + "px";
      g.style.top = r.top + "px";
      document.body.appendChild(g);
      g.animate([{ opacity: .55, transform: "scale(.95)" },
                 { opacity: 0, transform: "scale(.35)" }],
                { duration: 460, easing: "ease-out" }).finished.then(() => g.remove());
    }, 42);

    await bolita.animate([
      { transform: "translate(0,0) scale(1,1)", offset: 0 },
      { transform: `translate(${dx * .05}px, -16px) scale(1.22,.80)`, offset: .16 },
      { transform: `translate(${dx * .52}px, ${dy * .38}px) scale(.78,1.34)`, offset: .55 },
      { transform: `translate(${dx * .99}px, ${dy * 1.04}px) scale(1.36,.68)`, offset: .84 },
      { transform: `translate(${dx}px, ${dy}px) scale(1,1)`, offset: 1 },
    ], { duration: 820, easing: "cubic-bezier(.42,.02,.24,1)", fill: "forwards" }).finished;

    await apertura;
    clearInterval(estela);
    onda(x1, y1, 62);

    // 3. La bolita se absorbe y el tick ocupa su sitio en el mismo instante.
    bolita.animate([{ transform: `translate(${dx}px,${dy}px) scale(1)`, opacity: 1 },
                    { transform: `translate(${dx}px,${dy}px) scale(.15)`, opacity: 0 }],
                   { duration: 220, easing: "cubic-bezier(.5,0,.75,0)" })
          .finished.then(() => bolita.remove());

    const el = pintarTick(contacto);
    el.classList.add("crm-tick--nuevo");
    hueco.replaceWith(el);
  }

  /* ── Las pestañas de fase del móvil ──────────
   * En el teléfono se enseña una columna cada vez. Deslizar a ciegas entre
   * seis columnas no dice en cuál estás; tocar la fase, sí.
   */
  (function () {
    const barra = document.getElementById("crm-fases");
    if (!barra) return;
    const mostrar = clave => {
      tablero.querySelectorAll("[data-etapa]").forEach(c =>
        c.classList.toggle("crm-col--oculta", c.dataset.etapa !== clave));
      barra.querySelectorAll(".crm-fase").forEach(b =>
        b.classList.toggle("crm-fase--on", b.dataset.fase === clave));
      try { sessionStorage.setItem("crm_fase", clave); } catch (e) {}
    };
    barra.addEventListener("click", e => {
      const b = e.target.closest(".crm-fase");
      if (b) mostrar(b.dataset.fase);
    });
    // Se recuerda la última mirada: al volver de una ficha no se pierde el sitio
    let guardada = null;
    try { guardada = sessionStorage.getItem("crm_fase"); } catch (e) {}

    /* Si no hay nada recordado, se abre por la primera fase CON gente. Abrir
     * siempre por «Nuevo» enseñaba «nadie en esta fase todavía» a quien tiene
     * seis leads repartidos por el resto del embudo. */
    const conGente = [...barra.querySelectorAll(".crm-fase")].find(b =>
      (tablero.querySelector(`[data-lista="${b.dataset.fase}"]`)?.children.length ?? 0) > 0);

    mostrar(guardada && barra.querySelector(`[data-fase="${guardada}"]`)
            ? guardada
            : (conGente || barra.querySelector(".crm-fase")).dataset.fase);
  })();

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

      document.querySelectorAll(".crm-etapa").forEach(b =>
        b.classList.toggle("crm-etapa--on", b.dataset.etapa === lead.etapa));

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

  /* Cambiar de fase desde la ficha. Sin esto, en el móvil —donde no se puede
   * arrastrar— un lead se quedaba atrapado en la fase en la que naciera. */
  document.querySelectorAll(".crm-etapa").forEach(boton => {
    boton.addEventListener("click", async () => {
      if (!abierto) return;
      const antes = document.querySelector(".crm-etapa--on");
      document.querySelectorAll(".crm-etapa").forEach(b => b.classList.remove("crm-etapa--on"));
      boton.classList.add("crm-etapa--on");
      try {
        const { lead } = await api(`/crm/leads/${abierto}/mover`, {
          method: "POST",
          body: JSON.stringify({ etapa: boton.dataset.etapa, posicion: 0 }),
        });
        // La tarjeta se va a la columna nueva y los contadores se ponen al día
        tablero.querySelector(`.crm-tarjeta[data-id="${lead.id}"]`)?.remove();
        tablero.querySelector(`[data-lista="${lead.etapa}"]`)?.prepend(pintarTarjeta(lead));
        contar();
        document.querySelectorAll(".crm-fase").forEach(f => {
          const n = tablero.querySelector(`[data-lista="${f.dataset.fase}"]`)?.children.length ?? 0;
          f.querySelector("i").textContent = n;
        });
      } catch (e) {
        document.querySelectorAll(".crm-etapa").forEach(b => b.classList.remove("crm-etapa--on"));
        antes?.classList.add("crm-etapa--on");
        alert(e.message);
      }
    });
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
