import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { AdminPage } from "./AdminPage";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{window.location.pathname === "/admin" ? <AdminPage /> : <App />}</React.StrictMode>,
);
