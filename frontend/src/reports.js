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
    label: "Disponibilidad por componente",
    grupo: "Detalle",
    endpoint: "horas-disponibilidad",
    componentesFor: (o) => maskForOps([o.ip && 155, o.inf && 156].filter(Boolean)),
    descripcion: "Componentes con indisponibilidad programada o forzada: % del período disponible y horas desconectadas.",
    defaults: { ip: true, inf: true },
    options: [
      { type: "checkbox", key: "ip", label: "Programada" },
      { type: "checkbox", key: "inf", label: "Forzada" },
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
];
