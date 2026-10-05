import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

import * as api from "../api";

// Las pruebas corren sin servidor: por defecto no hay sesión ni se exige (modo demostración).
beforeEach(() => {
  vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: false, sesion: null });
});
