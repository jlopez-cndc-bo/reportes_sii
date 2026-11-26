// Metadatos de los 3 reportes: opciones específicas y armado del request.
// getIds(tipo) devuelve los id_objeto seleccionados del árbol para un tipo
// de nodo ("componente" | "central" | "agente").
//
// El alcance del árbol (bitmask de tipos de componente) se deriva de los
// tipos de operación que consulta cada reporte, según qué componentes
// registran eventos de cada tipo en dc_eventos (dato de negocio):
//   152 Op.Normal / 153 Pot.Limitada → sólo GENERADOR
//   155 Programada / 156 Forzada     → los 8 tipos
//   158 Prueba                       → todos menos ALIMENTA y CAP-SERIE
// Bits: ALIMENTA=1 AUTOTRAN=2 CAP-SERIE=4 CAP-SHUNT=8 GENERADOR=16
//       LINEA=32 REACTOR=64 TRANSFOR=128
export const COMPONENTES_GENERADOR = 16;
export const COMPONENTES_TODOS = 255;

const OP_COMPONENTES = {
  152: COMPONENTES_GENERADOR,
  153: COMPONENTES_GENERADOR,
  155: COMPONENTES_TODOS,
  156: COMPONENTES_TODOS,
  158: COMPONENTES_TODOS & ~1 & ~4,
  192: COMPONENTES_TODOS,
};

// Unión de máscaras para los tipos de operación activos del reporte;
// sin selección cae a GENERADOR para no dejar el árbol vacío.
const maskForOps = (ops) =>
  ops.reduce((m, o) => m | (OP_COMPONENTES[o] || 0), 0) || COMPONENTES_GENERADOR;

export const REPORTS = [
  {
    id: "horas-disponibilidad",
    label: "Disponibilidad",
    grupo: "Detalle",
    endpoint: "horas-disponibilidad",
    // Nivel Central sólo aplica a generadores (la central sale de la tabla de potencia efectiva).
    componentesFor: (o) => (o.nivel === "central" ? COMPONENTES_GENERADOR
      : maskForOps([o.ip && 155, o.inf && 156].filter(Boolean))),
    descripcion: "% del período disponible y horas desconectadas por indisponibilidad programada o forzada. Por componente: sólo los que tuvieron eventos. Por central: todas sus unidades, ponderadas por su potencia efectiva oficial.",
    defaults: { nivel: "componente", ip: true, inf: true },
    options: [
      {
        type: "radio", key: "nivel", label: "Nivel",
        options: [
          { value: "componente", label: "Componente" },
          { value: "central", label: "Central" },
        ],
      },
      { type: "checkbox", key: "ip", label: "Programada" },
      { type: "checkbox", key: "inf", label: "Forzada" },
    ],
    buildBody: (shared, opt, getIds) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      unidades: getIds("componente"),
      ip: opt.ip,
      inf: opt.inf,
      nivel: opt.nivel,
    }),
  },
  {
    id: "horas-no-disponibilidad",
    label: "Eventos",
    grupo: "Detalle",
    endpoint: "horas-no-disponibilidad",
    componentesFor: (o) => maskForOps(
      [o.ip && 155, o.inf && 156, o.opn && 152, o.plim && 153].filter(Boolean)),
    descripcion: "Cada evento con su hora de ingreso y salida, tipo de operación, causa y restricción de gas.",
    defaults: { ip: true, inf: true, opn: false, plim: false, agregado: false },
    options: [
      { type: "checkbox", key: "ip", label: "Programada" },
      { type: "checkbox", key: "inf", label: "Forzada" },
      { type: "checkbox", key: "opn", label: "Operación normal" },
      { type: "checkbox", key: "plim", label: "Potencia limitada" },
      {
        type: "checkbox", key: "agregado", wide: true,
        label: "Unir eventos consecutivos del mismo componente",
        title: "Une en una sola fila los eventos de un componente cuando uno empieza a la misma hora en que termina el anterior (por ejemplo, un evento partido por día). Suma las horas y conserva el tipo y la causa del primero.",
      },
    ],
    buildBody: (shared, opt, getIds) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      unidades: getIds("componente"),
      ip: opt.ip,
      inf: opt.inf,
      opn: opt.opn,
      plim: opt.plim,
      agregado: opt.agregado,
    }),
  },
  {
    id: "horas-tipo-operacion",
    label: "Horas por tipo de operación",
    grupo: "Detalle",
    endpoint: "horas-tipo-operacion",
    componentesFor: (o) => maskForOps(
      [o.op_normal && 152, o.pot_limitada && 153, o.programada && 155,
       o.forzada && 156, o.prueba && 158, o.reprogramacion && 192].filter(Boolean)),
    descripcion: "Horas de cada componente en los tipos de operación marcados, por día, mes o año: una columna con el total o una por tipo.",
    defaults: {
      periodo: "dia",
      modo: "agregado",
      op_normal: true, pot_limitada: true, programada: true,
      forzada: true, prueba: true, reprogramacion: true,
    },
    options: [
      {
        type: "radio", key: "periodo", label: "Período",
        options: [
          { value: "dia", label: "Día" },
          { value: "mes", label: "Mes" },
          { value: "anio", label: "Año" },
        ],
      },
      {
        type: "radio", key: "modo", label: "Columnas",
        options: [
          { value: "agregado", label: "Total" },
          { value: "desagregado", label: "Una por tipo" },
        ],
      },
      { type: "checkbox", key: "op_normal", label: "Operación normal" },
      { type: "checkbox", key: "pot_limitada", label: "Potencia limitada" },
      { type: "checkbox", key: "programada", label: "Programada" },
      { type: "checkbox", key: "forzada", label: "Forzada" },
      { type: "checkbox", key: "prueba", label: "Prueba" },
      { type: "checkbox", key: "reprogramacion", label: "Reprogramación" },
    ],
    buildBody: (shared, opt, getIds) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      unidades: getIds("componente"),
      periodo: opt.periodo,
      modo: opt.modo,
      tipos_operacion: {
        op_normal: opt.op_normal,
        pot_limitada: opt.pot_limitada,
        programada: opt.programada,
        forzada: opt.forzada,
        prueba: opt.prueba,
        reprogramacion: opt.reprogramacion,
      },
    }),
  },
  {
    id: "indices",
    // Oculto hasta que Operaciones valide las reglas (correo 26/11/2026); el endpoint sigue activo.
    oculto: true,
    label: "Desempeño (FOR, EFOR, EFORd)",
    grupo: "Índices",
    endpoint: "indices",
    componentesFor: () => COMPONENTES_GENERADOR,
    descripcion: "Por generador marcado: FOR = FOH/(FOH+SH); EFOR = (FOH+EFDH)/(FOH+SH+EFDHRS); EFORd = (f·FOH+fp·EFDH)/(SH+f·FOH). "
      + "SH: horas en operación normal o limitada. RSH: horas en reserva (sin eventos). AH = SH+RSH. "
      + "FOH: horas en forzada que viene de operación normal o limitada (salida forzada). "
      + "Ind. en reserva: horas en forzada que viene de parada por falla en el arranque. "
      + "EFDH = Σ(Plimitada·t)/Pefectiva + Ind. en reserva/RSH; EFDHRS = Ind. en reserva/RSH. "
      + "f = (1/r+1/T)/(1/r+1/T+1/D), con r = FOH/salidas, T = RSH/arranques intentados, D = SH/arranques exitosos; fp = SH/AH. "
      + "Cálculo provisional según el documento de Operaciones del 24/11/2026.",
    defaults: {},
    options: [],
    buildBody: (shared, opt, getIds) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      unidades: getIds("componente"),
    }),
  },
  {
    id: "punta-temperatura",
    label: "Potencia de punta y temperatura",
    grupo: "Temperatura",
    endpoint: "punta-temperatura",
    sinArbol: true,
    componentesFor: () => COMPONENTES_GENERADOR,
    descripcion: "Por día: potencia de punta del SIN (retiros SMEC, MW), su hora y la temperatura de cada zona térmica en esa hora, con la correlación entre la temperatura máxima y la punta.",
    defaults: {},
    options: [],
    buildBody: (shared) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
    }),
  },
  {
    id: "temperatura-consulta",
    label: "Consulta de temperaturas",
    grupo: "Temperatura",
    endpoint: "temperatura-consulta",
    sinArbol: true,
    grafico: true,
    unidad: "°C",
    componentesFor: () => COMPONENTES_GENERADOR,
    descripcion: "Temperatura horaria de las zonas térmicas elegidas: las horas en columnas y una fila por fecha y zona, agrupadas por fecha, con la máxima, la mínima y el promedio del día. Se ve como tabla o gráfico.",
    defaults: { zonas: null },
    options: [
      { type: "checklist", key: "zonas", label: "Zonas", source: "zonas", hint: "Vienen todas marcadas; desmarque las que no quiera ver." },
    ],
    buildBody: (shared, opt) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      zonas: opt.zonas || [],
    }),
  },
  {
    id: "potencia-temperatura",
    label: "Potencia térmica por temperatura",
    grupo: "Potencia",
    endpoint: "potencia-temperatura",
    sinArbol: true,
    grafico: true,
    unidad: "MW",
    componentesFor: () => COMPONENTES_GENERADOR,
    descripcion: "Potencia efectiva de cada unidad térmica a la temperatura horaria de su zona (curva vigente potencia–temperatura), frente a la potencia efectiva oficial a temperatura media. Opcional: lo medido por el medidor propio en SMEC y el margen. Hasta 31 días.",
    defaults: { nivel: "zona", smec: false },
    options: [
      {
        type: "radio", key: "nivel", label: "Nivel",
        options: [{ value: "zona", label: "Zona térmica" }, { value: "unidad", label: "Unidad" }],
      },
      { type: "checkbox", key: "smec", label: "Comparar con lo medido en SMEC", wide: true,
        title: "Sólo unidades con medidor propio en SMEC; agrega lo medido (promedio de la hora) y el margen." },
    ],
    buildBody: (shared, opt) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      nivel: opt.nivel,
      smec: opt.smec,
    }),
  },
].filter((r) => !r.oculto);
