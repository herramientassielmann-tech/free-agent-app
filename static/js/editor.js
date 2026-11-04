/* Editor de guiones — comportamiento compartido.
 *
 * Un guión no nace cerrado: se edita desde el primer momento, esté donde esté
 * (generador, historial o ideas iniciales). Para no tener tres editores que se
 * separen con el tiempo, el comportamiento vive aquí y cada pantalla lo enchufa.
 *
 * Uso:
 *   EditorGuiones.init({
 *     raiz:         document.getElementById('...'),   // contenedor
 *     urlGuardar:   '/editor/guion/12/guardar',       // null = todavía no guardable
 *     urlRestaurar: '/editor/guion/12/restaurar',     // opcional
 *   });
 */
window.EditorGuiones = (function () {
  const SECCIONES = ["hook", "development", "conclusion", "caption"];
  // El caption se escribe, no se dice: no suma a la duración del vídeo.
  const HABLADAS = ["hook", "development", "conclusion"];
  // Ritmo de habla en vídeo corto en español: ~175 palabras por minuto.
  const PALABRAS_POR_SEG = 175 / 60;

  function pinta(seg) {
    if (seg < 1) return "—";
    return seg < 60
      ? Math.round(seg) + "s"
      : Math.floor(seg / 60) + "m " + Math.round(seg % 60) + "s";
  }

  /* «¡Copiado!» un momento y vuelta al botón de antes. Se guarda y se restaura
     el innerHTML, no el textContent: el botón lleva dentro un
     <span class="solo-ancho"> que el móvil esconde, y textContent lo aplanaba,
     así que después de copiar la palabra reaparecía en el teléfono. */
  function avisarCopiado(boton) {
    const antes = boton.innerHTML;
    boton.textContent = "¡Copiado!";
    setTimeout(() => { boton.innerHTML = antes; }, 1500);
  }

  function init(cfg) {
    const raiz = cfg.raiz;
    if (!raiz) return null;

    const campos = {};
    SECCIONES.forEach(s => {
      campos[s] = raiz.querySelector(`[data-seccion="${s}"]`);
    });
    if (!campos.hook) return null;

    const estado = raiz.querySelector("[data-ed-estado]");

    let urlGuardar = cfg.urlGuardar || null;
    let temporizador = null;
    let sinGuardar = false;
    // Los bloques del guion por tomas (ver pintarFormato); null en los de siempre
    let formatoActual = null;

    /* `resto` es la parte que sólo se lee en pantalla grande: va dentro de un
       <span class="solo-ancho">, que el móvil esconde. Antes esto escribía con
       textContent, se llevaba por delante el span de la plantilla y en el
       teléfono reaparecía la frase entera — justo la que no cabe en la barra. */
    function marcar(texto, clase, resto) {
      if (!estado) return;
      estado.textContent = texto;
      if (resto) {
        const largo = document.createElement("span");
        largo.className = "solo-ancho";
        largo.textContent = resto;
        estado.appendChild(largo);
      }
      estado.dataset.edEstado = clase;
    }

    function segundos(el) {
      const t = (el.innerText || "").trim();
      return (t ? t.split(/\s+/).length : 0) / PALABRAS_POR_SEG;
    }

    function recalcular() {
      HABLADAS.forEach(s => {
        const el = campos[s];
        if (!el) return;
        const marca = raiz.querySelector(`.ed-dur[data-for="${s}"]`);
        if (!marca) return;
        const seg = segundos(el);
        marca.textContent = pinta(seg);
        // El hook, según la metodología, va entre 1 y 3 segundos
        marca.classList.toggle("ed-dur--alerta", s === "hook" && seg > 3.5);
      });
      duracionFormato();
    }

    async function guardar() {
      if (!urlGuardar) return;
      const cuerpo = {};
      SECCIONES.forEach(s => { if (campos[s]) cuerpo[s] = campos[s].innerHTML; });
      // Por tomas mandan los bloques: el servidor saca de ellos las secciones
      if (formatoActual) cuerpo.formato = formatoActual;
      marcar("Guardando…", "guardando");
      try {
        const res = await fetch(urlGuardar, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cuerpo),
        });
        if (!res.ok) throw new Error();
        sinGuardar = false;
        marcar("Guardado ✓", "guardado");
        setTimeout(() => { if (!sinGuardar) marcar("Guardado ✓", "editado"); }, 2000);
      } catch (e) {
        marcar("No se pudo guardar", "error");
      }
    }

    function alEscribir() {
      sinGuardar = true;
      marcar("Sin guardar…", "pendiente");
      recalcular();
      clearTimeout(temporizador);
      temporizador = setTimeout(guardar, 1200);
    }

    SECCIONES.forEach(s => {
      const el = campos[s];
      if (!el) return;
      el.setAttribute("contenteditable", "true");
      el.setAttribute("role", "textbox");
      el.setAttribute("aria-multiline", "true");
      el.classList.add("ed-edit");
      el.addEventListener("input", alEscribir);
      // Pegar siempre en plano: si no, entra el formato del sitio de origen
      el.addEventListener("paste", e => {
        e.preventDefault();
        const txt = (e.clipboardData || window.clipboardData).getData("text/plain");
        document.execCommand("insertText", false, txt);
      });
    });

    raiz.querySelectorAll(".ed-tool[data-cmd]").forEach(b => {
      b.addEventListener("mousedown", e => e.preventDefault());  // no perder el cursor
      b.addEventListener("click", () => {
        document.execCommand(b.dataset.cmd, false, null);
        alEscribir();
      });
    });

    document.addEventListener("keydown", e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault(); clearTimeout(temporizador); guardar();
      }
    });

    window.addEventListener("beforeunload", e => {
      if (sinGuardar) { e.preventDefault(); e.returnValue = ""; }
    });

    const btnRestaurar = raiz.querySelector("[data-ed-restaurar]");
    if (btnRestaurar && cfg.urlRestaurar) {
      btnRestaurar.addEventListener("click", async () => {
        if (!confirm("Se perderán tus cambios y volverá el guión original. ¿Seguro?")) return;
        try {
          const res = await fetch(cfg.urlRestaurar, { method: "POST" });
          if (!res.ok) throw new Error();
          const data = await res.json();
          SECCIONES.forEach(s => {
            if (campos[s]) campos[s].textContent = data.secciones[s] || "";
          });
          ponerFormato(data.formato || null);
          sinGuardar = false;
          marcar("Original restaurado", "guardado");
          recalcular();
        } catch (e) {
          marcar("No se pudo restaurar", "error");
        }
      });
    }

    const btnCopiar = raiz.querySelector("[data-ed-copiar]");
    if (btnCopiar) {
      btnCopiar.addEventListener("click", () => {
        const porTomas = formatoActual ? lineasFormato(formatoActual) : null;
        const t = s => porTomas && s !== "caption"
          ? porTomas[s]
          : (campos[s] ? (campos[s].innerText || "").trim() : "");
        navigator.clipboard.writeText(
          `🎣 HOOK\n${t("hook")}\n\n📖 DESARROLLO\n${t("development")}\n\n` +
          `✅ CTA\n${t("conclusion")}\n\n📲 CAPTION\n${t("caption")}`
        );
        avisarCopiado(btnCopiar);
      });
    }

    const btnPdf = raiz.querySelector("[data-ed-pdf]");
    if (btnPdf) {
      btnPdf.addEventListener("click", async () => {
        if (sinGuardar) { clearTimeout(temporizador); await guardar(); }
        window.print();
      });
    }

    /* ── Tu guion / Vídeo de referencia ─────────────────────────────
       Un selector de dos posiciones. No hay más estado que el atributo
       data-mostrando del contenedor (no data-vista, que es el de los botones:
       con el mismo nombre, el contenedor se colaba en los selectores de ellos): el CSS enseña una cosa u otra a partir de
       ahí, y la impresión fuerza siempre el guion, así que el PDF sale bien
       aunque se le dé a imprimir con la transcripción a la vista. */
    const contenedor = raiz.querySelector(".script-sections");
    const selector = raiz.querySelector("[data-ed-vista]");
    const transTexto = raiz.querySelector("[data-ed-trans-texto]");

    function mostrar(vista) {
      if (!contenedor || !selector) return;
      contenedor.dataset.mostrando = vista;
      selector.querySelectorAll("[data-vista]").forEach(b =>
        b.setAttribute("aria-selected", b.dataset.vista === vista ? "true" : "false"));
    }

    if (selector) {
      selector.addEventListener("click", e => {
        const b = e.target.closest("[data-vista]");
        if (b) mostrar(b.dataset.vista);
      });
      // Flechas izquierda y derecha, como cualquier grupo de pestañas.
      selector.addEventListener("keydown", e => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        const destino = contenedor.dataset.mostrando === "guion" ? "referencia" : "guion";
        mostrar(destino);
        selector.querySelector(`[data-vista="${destino}"]`).focus();
        e.preventDefault();
      });
    }

    /* La transcripción partida en hook / desarrollo / CTA. Se pide nada más
       cargar, sin esperar al clic, para que al cambiar ya esté ordenada; la
       primera vez la parte la IA (un par de segundos) y luego queda guardada.
       Mientras tanto se ve de un bloque, sin editar. */
    const trans = raiz.querySelector("[data-ed-trans]");
    const partesEl = trans ? [...trans.querySelectorAll("[data-ed-parte]")] : [];
    const btnRestaurarTrans = raiz.querySelector("[data-ed-restaurar-trans]");

    // En los guiones por tomas, el original también va por tomas (misma forma
    // que el adaptado, para compararlos toma con toma). null si no.
    const refRaiz = trans ? trans.querySelector("[data-ed-trans-formato]") : null;
    let formatoRef = null;

    function pintarRefFormato(fm, editada) {
      formatoRef = JSON.parse(JSON.stringify(fm));
      partesEl.forEach(el => { el.closest("[data-ed-parte-card]").hidden = true; });
      trans.querySelector("[data-ed-trans-entero]").hidden = true;
      refRaiz.hidden = false;
      pintarFormato(formatoRef, refRaiz, false);
      trans.dataset.partida = "si";
      if (btnRestaurarTrans) btnRestaurarTrans.hidden = !editada;
    }

    function pintarPartes(partes, editada) {
      if (!trans) return;
      formatoRef = null;
      if (refRaiz) { refRaiz.hidden = true; refRaiz.replaceChildren(); }
      const hay = !!partes;
      partesEl.forEach(el => {
        el.textContent = hay ? (partes[el.dataset.edParte] || "") : "";
        el.closest("[data-ed-parte-card]").hidden = !hay;
      });
      trans.querySelector("[data-ed-trans-entero]").hidden = hay;
      trans.dataset.partida = hay ? "si" : "no";
      if (btnRestaurarTrans) btnRestaurarTrans.hidden = !editada;
    }

    async function pedirPartes() {
      if (!trans || !trans.dataset.url || trans.dataset.partida === "si") return;
      if (!(transTexto.textContent || "").trim()) return;
      const estado = trans.querySelector("[data-ed-trans-estado]");
      if (estado) estado.textContent = "Ordenando por secciones…";
      try {
        const r = await fetch(trans.dataset.url, { credentials: "same-origin" });
        const d = r.ok ? await r.json() : {};
        if (d.formato && refRaiz) pintarRefFormato(d.formato, d.editada);
        else pintarPartes(d.partes || null, d.editada);
      } catch (_) {
        pintarPartes(null);
      }
      if (estado) estado.textContent = "Lo que se dice en el vídeo, tal cual";
    }

    /* Editar la transcripción. Se guarda sola, aparte del guion y con su
       propia ruta: el original sigue en la base y «Restaurar original» lo trae. */
    let tempTrans = null;
    let transSinGuardar = false;

    async function guardarTrans() {
      if (!trans || !trans.dataset.url) return;
      clearTimeout(tempTrans);
      const url = trans.dataset.url;
      const cuerpo = {};
      if (formatoRef) cuerpo.formato = formatoRef;
      else partesEl.forEach(el => { cuerpo[el.dataset.edParte] = (el.innerText || "").trim(); });
      marcar("Guardando…", "guardando");
      try {
        const res = await fetch(url + "/guardar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cuerpo),
        });
        if (!res.ok) throw new Error();
        transSinGuardar = false;
        if (btnRestaurarTrans && trans.dataset.url === url) btnRestaurarTrans.hidden = false;
        marcar("Guardado ✓", "guardado");
        setTimeout(() => { if (!transSinGuardar && !sinGuardar) marcar("Guardado ✓", "editado"); }, 2000);
      } catch (e) {
        marcar("No se pudo guardar", "error");
      }
    }

    function alEscribirTrans() {
      transSinGuardar = true;
      marcar("Sin guardar…", "pendiente");
      clearTimeout(tempTrans);
      tempTrans = setTimeout(guardarTrans, 1200);
    }

    if (refRaiz) {
      refRaiz.addEventListener("input", e => {
        const campo = e.target.closest("[data-campo]");
        if (!campo || !formatoRef) return;
        formatoRef.bloques[+campo.dataset.i][campo.dataset.campo] = (campo.innerText || "").trim();
        alEscribirTrans();
      });
    }

    partesEl.forEach(el => {
      el.addEventListener("input", alEscribirTrans);
      // Pegar siempre en plano, como en el guion
      el.addEventListener("paste", e => {
        e.preventDefault();
        const txt = (e.clipboardData || window.clipboardData).getData("text/plain");
        document.execCommand("insertText", false, txt);
      });
    });

    window.addEventListener("beforeunload", e => {
      if (transSinGuardar) { e.preventDefault(); e.returnValue = ""; }
    });

    if (btnRestaurarTrans) {
      btnRestaurarTrans.addEventListener("click", async () => {
        if (!confirm("Se perderán tus cambios y volverá la transcripción original del vídeo. ¿Seguro?")) return;
        clearTimeout(tempTrans);
        try {
          const res = await fetch(trans.dataset.url + "/restaurar", { method: "POST" });
          if (!res.ok) throw new Error();
          const d = await res.json();
          transSinGuardar = false;
          if (d.formato && refRaiz) pintarRefFormato(d.formato, false);
          else pintarPartes(d.partes || null, false);
          marcar("Original restaurado", "guardado");
        } catch (e) {
          marcar("No se pudo restaurar", "error");
        }
      });
    }

    // Copia lo que se ve: con los cambios, si los hay.
    const btnCopiarTrans = raiz.querySelector("[data-ed-copiar-trans]");
    if (btnCopiarTrans && transTexto) {
      btnCopiarTrans.addEventListener("click", () => {
        const texto = formatoRef
          ? formatoRef.bloques.map(b => [b.texto, b.extra].filter(Boolean).join(" ")).join("\n\n")
          : trans && trans.dataset.partida === "si"
          ? partesEl.map(el => (el.innerText || "").trim()).filter(Boolean).join("\n\n")
          : (transTexto.textContent || "").trim();
        navigator.clipboard.writeText(texto);
        avisarCopiado(btnCopiarTrans);
      });
    }

    /* El generador no tiene la transcripción hasta que la IA responde: se la
       pasa aquí, con la ruta para partirla. Sin texto, el selector no se
       enseña (no hay nada que ver). Si había un cambio pendiente en el guion
       anterior, se guarda antes de cambiar de ruta. */
    function ponerTranscripcion(texto, url) {
      if (!transTexto || !selector) return;
      if (transSinGuardar) guardarTrans();
      transTexto.textContent = texto || "";
      selector.hidden = !texto;
      if (trans) trans.dataset.url = url || "";
      pintarPartes(null);
      mostrar("guion");
      pedirPartes();
    }

    /* ── Guion por tomas ─────────────────────────────────────────────
       El realtor graba leyendo un trozo corto, diciéndolo de memoria y
       pasando al siguiente. Cada bloque es una toma, y el diseño cambia con el
       formato del vídeo. Las etiquetas (1, 2, TOMA, PISTA, 🎤 TÚ…) las pone
       esto, no la IA: el bloque solo trae parte, texto y, según el tipo,
       extra / quien / rol. Ver app/services/formato.py. */
    const fmRaiz = raiz.querySelector("[data-ed-formato]");
    const NOMBRE_TIPO = { lista: "Lista", pares: "Pares", dialogo: "Diálogo",
                          adivina: "Adivina", historia: "Historia" };
    const COLOR_PARTE = { hook: "badge-blue", desarrollo: "badge-orange", cta: "badge-green" };

    // Lo que dice el propio realtor (en un diálogo, lo de la otra voz no)
    const loDiceEl = (fm, b) => !(fm.tipo === "dialogo" && b.quien === "otro");
    // En lista y pares, un elemento es lo que trae las dos columnas
    const esElemento = (fm, b) => (fm.tipo === "lista" || fm.tipo === "pares") && !!b.extra;

    /* Las mismas líneas que derivar_secciones() en el servidor, para Copiar */
    function lineasFormato(fm) {
      const l = { hook: [], development: [], conclusion: [] };
      const clave = { hook: "hook", desarrollo: "development", cta: "conclusion" };
      fm.bloques.forEach(b => {
        let t = b.texto || "";
        if (b.extra) t = t ? t + (fm.tipo === "pares" ? " → " : ": ") + b.extra : b.extra;
        else if (fm.tipo === "dialogo" && b.quien === "otro") t = "— " + t;
        l[clave[b.parte]].push(t);
      });
      return { hook: l.hook.join("\n"), development: l.development.join("\n"),
               conclusion: l.conclusion.join("\n") };
    }

    function el(tag, clase, texto) {
      const e = document.createElement(tag);
      if (clase) e.className = clase;
      if (texto != null) e.textContent = texto;
      return e;
    }

    function editable(i, campo, texto, clase) {
      const e = el("div", "fm-edit " + (clase || ""), texto || "");
      e.setAttribute("contenteditable", "plaintext-only");
      e.setAttribute("role", "textbox");
      e.dataset.i = i;
      e.dataset.campo = campo;
      return e;
    }

    function duracionFormato() {
      const marca = fmRaiz && fmRaiz.querySelector("[data-fm-dur]");
      if (!marca || !formatoActual) return;
      const palabras = formatoActual.bloques
        .filter(b => loDiceEl(formatoActual, b))
        .reduce((n, b) => n + ((b.texto || "") + " " + (b.extra || "")).trim().split(/\s+/).filter(Boolean).length, 0);
      marca.textContent = "≈ " + pinta(palabras / PALABRAS_POR_SEG);
    }

    /* Pinta un guion por tomas en `destino`: el adaptado (con su cabecera de
       formato, tomas y duración) o el original del vídeo de referencia, que
       usa la misma forma para compararlos toma con toma. */
    function pintarFormato(fm, destino = fmRaiz, conCabecera = true) {
      destino.replaceChildren();
      const tomas = fm.bloques.filter(b => loDiceEl(fm, b)).length;

      const cab = el("div", "fm-cabecera ed-no-print");
      cab.append(el("span", "fm-tipo", "Formato: " + (NOMBRE_TIPO[fm.tipo] || "Historia")),
                 el("span", null, tomas + (tomas === 1 ? " toma" : " tomas")));
      const dur = el("span"); dur.dataset.fmDur = ""; cab.append(dur);
      cab.append(el("span", "fm-ayuda", fm.tipo === "dialogo"
        ? "Las tomas con número las dices tú; las 💬 las dice otra persona o van en pantalla."
        : "Lee una toma, dila de memoria a cámara y pasa a la siguiente."));
      if (conCabecera) destino.append(cab);

      const deLista = fm.tipo === "lista" || fm.tipo === "pares";
      if (deLista && !fm.bloques.some(b => b.parte === "hook" && !b.extra)) {
        destino.append(el("div", "fm-aviso", "▶ Sin frase de entrada: empieza directo con el 1."));
      }

      let nTomas = 0, nElem = 0, nPista = 0;
      // Cada parte (HOOK, DESARROLLO, CTA) se nombra en su primera toma: el
      // color sigue en todas, y la palabra deja claro dónde empieza cada una
      // sin gastar una línea más en cada toma.
      const nombrada = new Set();
      const nombre = parte => {
        if (nombrada.has(parte)) return "";
        nombrada.add(parte);
        return { hook: "HOOK", desarrollo: "DESARROLLO", cta: "CTA" }[parte];
      };
      fm.bloques.forEach((b, i) => {
        const dice = loDiceEl(fm, b);
        const elem = esElemento(fm, b);
        const fila = el("div", "fm-toma fm-toma--" + b.parte);

        let num = "", etiqueta = "", color = COLOR_PARTE[b.parte];
        if (deLista) {
          if (elem) num = String(++nElem);
          else if (b.parte === "desarrollo") { num = "↳"; fila.classList.add("fm-toma--sigue"); }
          else etiqueta = b.parte === "hook" ? "ENTRADA" : "CTA";
        } else if (fm.tipo === "dialogo") {
          // Lo tuyo lleva número; la parte, en la primera toma de cada una
          if (dice) { num = String(++nTomas); etiqueta = nombre(b.parte); }
          else { num = "💬"; fila.classList.add("fm-toma--otro"); }
        } else {
          num = String(++nTomas);
          if (fm.tipo === "adivina" && b.parte === "hook") etiqueta = "PREGUNTA";
          else if (b.rol === "pista") etiqueta = "PISTA " + (++nPista);
          else if (b.rol === "respuesta") { etiqueta = "RESPUESTA"; color = "badge-purple";
                                           fila.classList.add("fm-toma--respuesta"); }
          else etiqueta = nombre(b.parte);
        }

        fila.append(el("div", "fm-num", num));
        const cuerpo = el("div", "fm-cuerpo");
        if (etiqueta) cuerpo.append(el("span", "badge " + color + " fm-etq", etiqueta));
        if (elem) {
          // El concepto arriba y lo que se dice de él debajo: se lee de arriba
          // abajo, como se graba, sin saltar de una columna a otra
          const par = el("div", "fm-par");
          par.append(editable(i, "texto", b.texto, "fm-concepto"),
                     editable(i, "extra", b.extra, "fm-extra"));
          cuerpo.append(par);
        } else {
          cuerpo.append(editable(i, "texto", b.texto, "fm-texto"));
        }
        fila.append(cuerpo);
        destino.append(fila);
      });
      if (destino === fmRaiz) duracionFormato();
    }

    function ponerFormato(fm) {
      formatoActual = fm && Array.isArray(fm.bloques) && fm.bloques.length
        ? JSON.parse(JSON.stringify(fm)) : null;
      if (!fmRaiz) return;
      fmRaiz.hidden = !formatoActual;
      if (contenedor) contenedor.toggleAttribute("data-con-formato", !!formatoActual);
      if (formatoActual) pintarFormato(formatoActual);
      else fmRaiz.replaceChildren();
    }

    if (fmRaiz) {
      fmRaiz.addEventListener("input", e => {
        const campo = e.target.closest("[data-campo]");
        if (!campo || !formatoActual) return;
        formatoActual.bloques[+campo.dataset.i][campo.dataset.campo] = (campo.innerText || "").trim();
        alEscribir();
      });
    }

    ponerFormato(cfg.formato || null);
    recalcular();
    pedirPartes();

    return {
      recalcular,
      ponerTranscripcion,
      ponerFormato,
      // El generador no conoce el id del guión hasta que la IA responde
      activarGuardado(url) { urlGuardar = url; marcar("Editable", "listo", " — escribe encima"); },
    };
  }

  return { init, SECCIONES };
})();
