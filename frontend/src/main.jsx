import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
// Tipografía incluida en el build (la app corre en red interna, sin CDN).
import "@fontsource/saira/latin-400.css";
import "@fontsource/saira/latin-500.css";
import "@fontsource/saira/latin-600.css";
import "@fontsource/saira-semi-condensed/latin-400.css";
import "@fontsource/saira-semi-condensed/latin-600.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
