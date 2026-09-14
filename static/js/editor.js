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
    }

    async function guardar() {
      if (!urlGuardar) return;
      const cuerpo = {};
      SECCIONES.forEach(s => { if (campos[s]) cuerpo[s] = campos[s].innerHTML; });
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
        const t = s => campos[s] ? (campos[s].innerText || "").trim() : "";
        navigator.clipboard.writeText(
          `🎣 HOOK\n${t("hook")}\n\n📖 DESARROLLO\n${t("development")}\n\n` +
          `✅ CTA\n${t("conclusion")}\n\n📲 CAPTION\n${t("caption")}`
        );
        const orig = btnCopiar.textContent;
        btnCopiar.textContent = "¡Copiado!";
        setTimeout(() => btnCopiar.textContent = orig, 1500);
      });
    }

    const btnPdf = raiz.querySelector("[data-ed-pdf]");
    if (btnPdf) {
      btnPdf.addEventListener("click", async () => {
        if (sinGuardar) { clearTimeout(temporizador); await guardar(); }
        window.print();
      });
    }

    recalcular();

    return {
      recalcular,
      // El generador no conoce el id del guión hasta que la IA responde
      activarGuardado(url) { urlGuardar = url; marcar("Editable", "listo", " — escribe encima"); },
    };
  }

  return { init, SECCIONES };
})();
