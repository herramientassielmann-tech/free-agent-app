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
    trozos.push(`<div class="crm-pie">
      ${l.origen ? '<span class="crm-origen"></span>' : ""}
      ${l.presupuesto ? '<span class="crm-presupuesto"></span>' : ""}
      <span class="crm-dias">${l.dias}d</span></div>`);
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
      const { lead, notas } = await api(`/crm/leads/${id}`);
      abierto = id;
      $("crm-panel-nombre").textContent = lead.nombre;
      $("crm-panel-meta").textContent =
        [lead.origen, lead.contacto, `${lead.dias} días sin contacto`]
          .filter(Boolean).join(" · ");

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

      panel.hidden = false; fondo.hidden = false;
    } catch (e) { alert(e.message); }
  }

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
      const { lead } = await api(`/crm/leads/${abierto}/contactado`, { method: "POST" });
      actualizarTarjeta(lead);
      abrirPanel(abierto);
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
