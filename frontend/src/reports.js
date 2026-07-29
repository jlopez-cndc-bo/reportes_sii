// Metadatos de los 5 reportes: opciones específicas y armado del request.
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
    id: "potencias-disponibles",
    label: "Disponibles",
    grupo: "Potencias",
    endpoint: "potencias-disponibles",
    // Consulta disponibilidad con Op.Normal + Programada + Forzada.
    componentesFor: () => maskForOps([152, 155, 156]),
    descripcion:
      "Disponibilidad (%) y potencia por Unidad, Central o Agente.",
    defaults: { nivel: "unidad" },
    options: [
      {
        type: "radio",
        key: "nivel",
        label: "Nivel",
        options: [
          { value: "unidad", label: "Unidad" },
          { value: "central", label: "Central" },
        ],
      },
    ],
    buildBody: (shared, opt, getIds) => {
      const tipo = opt.nivel === "central" ? "central" : "componente";
      return {
        fecha_inicio: shared.fechaInicio,
        fecha_fin: shared.fechaFin,
        nivel: opt.nivel,
        unidades: getIds(tipo),
      };
    },
  },
  {
    id: "potencias-indisponibles",
    label: "Indisponibles",
    grupo: "Potencias",
    endpoint: "potencias-indisponibles",
    componentesFor: (o) => maskForOps([o.ip && 155, o.inf && 156].filter(Boolean)),
    descripcion:
      "Potencia indisponible por generador, pivoteada por intervalo de tiempo.",
    defaults: { resolucion: "minuto", intervalo_minutos: 15, horas: 1, ip: true, inf: true },
    options: [
      {
        type: "radio",
        key: "resolucion",
        label: "Resolución",
        options: [
          { value: "minuto", label: "Minutos" },
          { value: "hora", label: "Horas" },
        ],
      },
      { type: "number", key: "intervalo_minutos", label: "Minutos", min: 1, max: 1440, showIf: (o) => o.resolucion === "minuto" },
      { type: "number", key: "horas", label: "Horas", min: 1, max: 24, showIf: (o) => o.resolucion === "hora" },
      { type: "checkbox", key: "ip", label: "Programada (155)" },
      { type: "checkbox", key: "inf", label: "Forzada (156)" },
    ],
    buildBody: (shared, opt, getIds) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      unidades: getIds("componente"),
      resolucion: opt.resolucion,
      intervalo_minutos: Number(opt.intervalo_minutos),
      horas: Number(opt.horas),
      ip: opt.ip,
      inf: opt.inf,
    }),
  },
  {
    id: "horas-disponibilidad",
    label: "Disponibilidad",
    grupo: "Horas",
    endpoint: "horas-disponibilidad",
    componentesFor: (o) => maskForOps([o.ip && 155, o.inf && 156].filter(Boolean)),
    descripcion: "% de disponibilidad, horas desconectadas y horas del período.",
    defaults: { ip: true, inf: true },
    options: [
      { type: "checkbox", key: "ip", label: "Programada (155)" },
      { type: "checkbox", key: "inf", label: "Forzada (156)" },
    ],
    buildBody: (shared, opt, getIds) => ({
      fecha_inicio: shared.fechaInicio,
      fecha_fin: shared.fechaFin,
      unidades: getIds("componente"),
      ip: opt.ip,
      inf: opt.inf,
    }),
  },
  {
    id: "horas-no-disponibilidad",
    label: "No Disponibilidad",
    grupo: "Horas",
    endpoint: "horas-no-disponibilidad",
    componentesFor: (o) => maskForOps(
      [o.ip && 155, o.inf && 156, o.opn && 152, o.plim && 153].filter(Boolean)),
    descripcion: "Detalle de eventos: ingreso/salida, causa, restricción de gas.",
    defaults: { ip: true, inf: true, opn: false, plim: false, agregado: false },
    options: [
      { type: "checkbox", key: "ip", label: "Programada (155)" },
      { type: "checkbox", key: "inf", label: "Forzada (156)" },
      { type: "checkbox", key: "opn", label: "Op. Normal (152)" },
      { type: "checkbox", key: "plim", label: "Pot. Limitada (153)" },
      { type: "checkbox", key: "agregado", label: "Agregar eventos contiguos" },
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
    label: "Por Tipo de Operación",
    grupo: "Horas",
    endpoint: "horas-tipo-operacion",
    componentesFor: (o) => maskForOps(
      [o.op_normal && 152, o.pot_limitada && 153, o.programada && 155,
       o.forzada && 156, o.prueba && 158, o.reprogramacion && 192].filter(Boolean)),
    descripcion: "Horas agregadas o desagregadas por tipo, en día / mes / año.",
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
        type: "radio", key: "modo", label: "Modo",
        options: [
          { value: "agregado", label: "Agregado" },
          { value: "desagregado", label: "Desagregado" },
        ],
      },
      { type: "checkbox", key: "op_normal", label: "Op. Normal (152)" },
      { type: "checkbox", key: "pot_limitada", label: "Pot. Limitada (153)" },
      { type: "checkbox", key: "programada", label: "Programada (155)" },
      { type: "checkbox", key: "forzada", label: "Forzada (156)" },
      { type: "checkbox", key: "prueba", label: "Prueba (158)" },
      { type: "checkbox", key: "reprogramacion", label: "Reprogramación (192)" },
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
];
