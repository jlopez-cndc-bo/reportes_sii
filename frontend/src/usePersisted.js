import { useEffect, useState } from "react";

// Set persistido en localStorage (guardado como array JSON).
export function usePersistedSet(key) {
  const [value, setValue] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(key) || "[]"));
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify([...value])); } catch {}
  }, [key, value]);
  return [value, setValue];
}

// useState persistido en localStorage (JSON). Tolera storage inaccesible.
export function usePersisted(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const s = localStorage.getItem(key);
      return s !== null ? JSON.parse(s) : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  }, [key, value]);
  return [value, setValue];
}
