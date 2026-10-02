import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

import * as api from "../api";
import { restaurarRolesBase } from "../app/roles";

// Las pruebas corren sin servidor: por defecto no hay sesión ni se exige (modo demostración).
beforeEach(() => {
  restaurarRolesBase();  // la lista de roles es compartida: ninguna prueba hereda los roles que otra registró
  vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: false, sesion: null });
  vi.spyOn(api, "listarRoles").mockRejectedValue(new Error("sin servidor"));  // queda el respaldo de la interfaz
});
