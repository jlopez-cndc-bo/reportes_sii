// Archivos del HFD de SCADA (cargados por rs7_core8 en el esquema SPECTRUM).
// `id` es el `archivo` de /api/hfd; `magnitudes` son los valores de `type`
// (también los lista GET /api/hfd/catalogo).

export const MAX_DIAS_HFD = 31;

// Confirmadas por el usuario (2026-11-19). Embalses y taps: sin confirmar, no se muestran.
export const UNIDADES = { P: "MW", Q: "MVAr", U: "kV", Uab: "kV", Ubc: "kV", Uac: "kV" };

export const SCADA_REPORTS = [
  {
    id: "generadores",
    label: "Generadores",
    grupo: "Registros",
    descripcion: "Potencia activa (P) y reactiva (Q) de cada unidad generadora (archivo TDM_GE30).",
    magnitudes: ["P", "Q"],
  },
  {
    id: "transferencias",
    label: "Transferencias",
    grupo: "Registros",
    descripcion: "Flujos P y Q medidos en cada extremo de líneas y transformadores (archivo TDM_TD30).",
    magnitudes: ["P", "Q"],
  },
  {
    id: "tensiones",
    label: "Tensiones",
    grupo: "Registros",
    descripcion: "Tensión de barras: U, y las de línea Uab, Ubc, Uac donde existen (archivo TDM_V30).",
    magnitudes: ["U", "Uab", "Ubc", "Uac"],
  },
  {
    id: "embalses",
    label: "Embalses",
    grupo: "Registros",
    descripcion: "Cota y nivel de embalses (archivo TDM_H30).",
    magnitudes: ["COTA_EMB", "NIV_EMB", "NIV_COMP"],
  },
  {
    id: "taps",
    label: "Taps de transformadores",
    grupo: "Registros",
    descripcion: "Posición del tap de transformadores, total y por fase (archivo TAP__1MM).",
    magnitudes: ["TAP", "TAP_A", "TAP_B", "TAP_C", "TapPosMv"],
  },
  {
    id: "bancos",
    label: "Bancos de capacitores (52)",
    grupo: "Registros",
    descripcion: "Estado del interruptor de cada banco de capacitores, una foto cada 15 minutos "
      + "(archivo 52_BCAP): 1 = cerrado, 0 = abierto, -1 = sin foto todavía ese día.",
    magnitudes: ["CB"],
  },
  // Consolidados con drill-down hasta la medida (POST /api/hfd/consolidados/{id}).
  // `fin`: usa rango Inicio/Final; si no, una sola fecha (como SMEC).
  {
    id: "generacion-tipo",
    label: "Generación por tecnología",
    grupo: "Consolidados",
    consolidado: true,
    fin: false,
    descripcion: "Potencia de generación de un día cada 15 minutos, por tecnología, central y unidad. "
      + "La tecnología sale del catálogo del HFD; el consumo propio (negativo) cuenta como 0.",
    extra: "Potencia en MW; energía en MWh",
  },
  {
    id: "energia-tipo",
    label: "Energía por tecnología",
    grupo: "Consolidados",
    consolidado: true,
    fin: true,
    descripcion: "Energía generada por día, por tecnología, central y unidad, con su participación en el SIN.",
    extra: "Energía en MWh",
  },
  {
    id: "demanda-departamento",
    label: "Demanda por departamento",
    grupo: "Consolidados",
    consolidado: true,
    fin: false,
    descripcion: "Demanda de cada departamento cada 15 minutos, con los elementos que la forman: "
      + "generación local y transferencias que entran o salen.",
    extra: "Potencia en MW; energía en MWh",
  },
];
