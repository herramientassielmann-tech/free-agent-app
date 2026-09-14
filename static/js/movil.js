/* Navegación del móvil.
 *
 * Va en su propio fichero y se carga desde base.html porque hace falta en
 * TODAS las páginas. app.js sólo se carga en el generador, así que meterlo
 * allí habría dejado el menú muerto en el resto de la app.
 */
(function () {
  const boton = document.getElementById("mov-mas");
  const hoja  = document.getElementById("mov-hoja");
  const fondo = document.getElementById("mov-fondo");
  if (!boton || !hoja || !fondo) return;

  const abrir = () => {
    hoja.hidden = fondo.hidden = false;
    requestAnimationFrame(() => hoja.classList.add("mov-hoja--abierta"));
    boton.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
  };
  const cerrar = () => {
    hoja.classList.remove("mov-hoja--abierta");
    boton.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
    setTimeout(() => { hoja.hidden = fondo.hidden = true; }, 260);
  };

  boton.addEventListener("click", () =>
    hoja.hidden ? abrir() : cerrar());
  fondo.addEventListener("click", cerrar);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !hoja.hidden) cerrar();
  });
})();
