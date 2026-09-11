/* Seguimiento semanal de alumnos.
 *
 * Cada número se guarda en cuanto cambia, sin botón de guardar y sin recargar.
 * No es un capricho: si hay que confirmar cada celda, el repaso del viernes
 * deja de hacerse a la tercera semana, y un seguimiento que no se rellena es
 * peor que no tenerlo, porque además engaña.
 */
(function () {
  const tabla = document.querySelector(".alu-tabla");
  if (!tabla) return;
  const lunes = tabla.dataset.lunes;

  async function guardar(fila, campo, valor) {
    const uid = fila.dataset.uid;
    const cuerpo = new URLSearchParams({ campo, valor });
    const res = await fetch(`/admin/alumnos/${uid}/${lunes}`, {
      method: "POST", body: cuerpo,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    if (!res.ok) throw new Error("No se pudo guardar");
    return res.json();
  }

  function pintar(fila, datos) {
    fila.querySelectorAll(".alu-num").forEach(i => {
      i.value = datos[i.dataset.campo];
    });
    const total = fila.querySelector("[data-total]");
    total.textContent = datos.publicados;
    total.classList.toggle("alu-total--ok", datos.cumple);
  }

  function avisarFallo(el) {
    el.classList.add("alu-fallo");
    setTimeout(() => el.classList.remove("alu-fallo"), 1600);
  }

  /* Un destello corto al guardar. Sin él no hay forma de saber si el clic
     ha llegado, y se acaba pulsando dos veces "por si acaso". */
  function destello(fila) {
    fila.classList.add("alu-guardado");
    setTimeout(() => fila.classList.remove("alu-guardado"), 600);
  }

  tabla.addEventListener("click", async e => {
    const boton = e.target.closest(".alu-mas-menos");
    if (!boton) return;
    const fila = boton.closest("tr");
    const campo = boton.dataset.campo;
    const input = fila.querySelector(`.alu-num[data-campo="${campo}"]`);
    const nuevo = Math.max(0, (parseInt(input.value, 10) || 0) + parseInt(boton.dataset.paso, 10));
    input.value = nuevo;                       // se ve al instante
    try {
      pintar(fila, await guardar(fila, campo, nuevo));
      destello(fila);
    } catch (err) { avisarFallo(input); }
  });

  tabla.addEventListener("change", async e => {
    const campo = e.target.dataset.campo;
    if (!campo) return;
    const fila = e.target.closest("tr");
    const valor = campo === "nota"
      ? e.target.value
      : Math.max(0, Math.min(99, parseInt(e.target.value, 10) || 0));
    if (campo !== "nota") e.target.value = valor;
    try {
      const datos = await guardar(fila, campo, valor);
      if (campo !== "nota") pintar(fila, datos);
      destello(fila);
    } catch (err) { avisarFallo(e.target); }
  });

  // Enter en una celda salta a la siguiente: rellenar la tabla entera sin
  // soltar el teclado es lo que hace que el repaso semanal dure dos minutos.
  tabla.addEventListener("keydown", e => {
    if (e.key !== "Enter" || !e.target.classList.contains("alu-num")) return;
    e.preventDefault();
    e.target.blur();
    const todos = [...tabla.querySelectorAll(".alu-num")];
    (todos[todos.indexOf(e.target) + 1] || todos[0]).focus();
  });
})();
