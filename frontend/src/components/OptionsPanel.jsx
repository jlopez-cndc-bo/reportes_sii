// Renderiza las opciones específicas de un reporte a partir de su descriptor.

export default function OptionsPanel({ options, values, onChange }) {
  const set = (key, val) => onChange({ ...values, [key]: val });

  return (
    <div className="options">
      {options.map((opt) => {
        if (opt.showIf && !opt.showIf(values)) return null;
        if (opt.type === "radio") {
          return (
            <div className="opt-group" key={opt.key}>
              <span className="opt-title">{opt.label}</span>
              <div className="opt-radios">
                {opt.options.map((o) => (
                  <button key={o.value} type="button"
                    className={`seg ${values[opt.key] === o.value ? "seg--on" : ""}`}
                    aria-pressed={values[opt.key] === o.value}
                    onClick={() => set(opt.key, o.value)}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          );
        }
        if (opt.type === "checkbox") {
          return (
            <label className="opt-check" key={opt.key}>
              <input
                type="checkbox"
                checked={!!values[opt.key]}
                onChange={(e) => set(opt.key, e.target.checked)}
              />
              {opt.label}
            </label>
          );
        }
        if (opt.type === "number") {
          return (
            <label className="opt-number" key={opt.key}>
              <span>{opt.label}</span>
              <input
                type="number"
                min={opt.min}
                max={opt.max}
                value={values[opt.key]}
                onChange={(e) => set(opt.key, e.target.value)}
              />
            </label>
          );
        }
        return null;
      })}
    </div>
  );
}
