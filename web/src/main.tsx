import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { captureToken } from "./api/token";
import "./index.css";

// FIRST, before the first render and before the first fetch: read the bearer token out of the URL
// fragment and erase it from the address bar.
captureToken();

const container = document.getElementById("root");
if (container === null) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
