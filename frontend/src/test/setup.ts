import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

import * as api from "../api";
import { restaurarRolesBase } from "../app/roles";

// Las pruebas corren sin servidor: la sesión la da `rolInicial` o `cuentaInicial` del router, o un mock de estadoSesion.
beforeEach(() => {
  restaurarRolesBase();  // la lista de roles es compartida: ninguna prueba hereda los roles que otra registró
  vi.spyOn(api, "estadoSesion").mockResolvedValue({ sesion: null, sin_cuentas: false });
  vi.spyOn(api, "listarRoles").mockRejectedValue(new Error("sin servidor"));  // queda el respaldo de la interfaz
});
