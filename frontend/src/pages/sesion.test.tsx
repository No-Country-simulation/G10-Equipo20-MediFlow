/**
 * Sesión del personal (RN-K5): con sesión, el rol y la firma son los de la cuenta; sin ella la aplicación
 * sigue en modo demostración, y una instalación con sesión obligatoria no muestra nada antes del ingreso.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const ANA = { usuario: "aud.ana", nombre: "Ana Torres", rol: "auditor_clinico" };
const ADMIN = { usuario: "admin.root", nombre: "Raíz", rol: "administrador" };
const USUARIOS = [
  { usuario: "aud.ana", nombre: "Ana Torres", rol: "auditor_clinico", tipo: "persona", activo: true, creado_por: "admin.root", creado_en: new Date().toISOString(), desactivado_en: null, con_clave: true },
  { usuario: "qf.maria", nombre: "María Gil", rol: "quimico_farmaceutico", tipo: "persona", activo: true, creado_por: "admin.root", creado_en: new Date().toISOString(), desactivado_en: null, con_clave: false },
];

function conSesion(cuenta: typeof ANA | null, exigir = false) {
  return vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: exigir, sesion: cuenta });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerResumen").mockResolvedValue({ total: 0, por_estado: {}, por_prioridad: {}, en_revision: 0, alertas_sin_acuse: 0, recetas_por_verificar: 0, ordenes_por_autorizar: 0, enrutados: 0, entregados_hoy: 0 });
  vi.spyOn(api, "listarUsuarios").mockResolvedValue(USUARIOS as never);
  vi.spyOn(api, "puestaEnMarcha").mockResolvedValue({ listo: false, requisitos: [] } as never);
  vi.spyOn(api, "obtenerPack").mockRejectedValue(new Error("sin pack"));
  vi.spyOn(api, "listarAccesos").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());

describe("sin sesión (modo demostración)", () => {
  it("se elige el rol, se firma con el nombre escrito y se ofrece iniciar sesión", async () => {
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    expect(await screen.findByLabelText(/firmo como/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Rol")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /iniciar sesión/i })).toHaveAttribute("href", "/ingresar");
    expect(screen.queryByTestId("sesion-activa")).toBeNull();
  });
});

describe("con sesión (RN-K5)", () => {
  it("el rol es el de la cuenta, aunque el navegador recuerde otro, y no se puede cambiar ni escribir otra firma", async () => {
    conSesion(ANA);
    render(<AppRouter rutaInicial="/revision" rolInicial="gestor" />);
    const sesion = await screen.findByTestId("sesion-activa");
    expect(sesion).toHaveTextContent("Ana Torres");
    expect(sesion).toHaveTextContent("Auditor clínico · aud.ana");
    expect(screen.queryByLabelText(/firmo como/i)).toBeNull();
    expect(screen.queryByLabelText("Rol")).toBeNull();
    expect(screen.queryByRole("link", { name: /iniciar sesión/i })).toBeNull();
    expect(screen.getByRole("link", { name: /cola de revisión/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Configuración" })).toBeNull();
  });

  it("las acciones se firman con la cuenta sin escribir el nombre", async () => {
    conSesion(ADMIN);
    const crear = vi.spyOn(api, "crearUsuario").mockResolvedValue({ ...USUARIOS[0], usuario: "jefe.rojas", rol: "jefe_urgencias" } as never);
    render(<AppRouter rutaInicial="/administracion" rolInicial="auditor_clinico" />);
    await screen.findByTestId("sesion-activa");
    await userEvent.type(await screen.findByLabelText(/nombre de usuario/i), "jefe.rojas");
    await userEvent.type(screen.getByLabelText(/nombre completo/i), "Andrés Rojas");
    await userEvent.type(screen.getByLabelText(/clave inicial/i), "turno-noche-2026");
    await userEvent.click(screen.getByRole("button", { name: /crear usuario/i }));
    await waitFor(() => expect(crear).toHaveBeenCalledWith({ usuario: "jefe.rojas", nombre: "Andrés Rojas", rol: "auditor_clinico", tipo: "persona", actor: "admin.root", clave: "turno-noche-2026" }));
  });

  it("cerrar sesión la cierra en el servidor y lleva al ingreso", async () => {
    conSesion(ANA);
    const cerrar = vi.spyOn(api, "cerrarSesion").mockResolvedValue();
    render(<AppRouter rutaInicial="/revision" />);
    await userEvent.click(await screen.findByRole("button", { name: /cerrar sesión/i }));
    await waitFor(() => expect(cerrar).toHaveBeenCalled());
    expect(await screen.findByRole("heading", { name: /iniciar sesión en mediflow/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /seguir sin sesión/i })).toBeInTheDocument();
  });

  it("si la sesión termina a mitad de trabajo, vuelve a pedirla", async () => {
    const estado = conSesion(ANA, true);
    render(<AppRouter rutaInicial="/revision" />);
    await screen.findByTestId("sesion-activa");
    estado.mockResolvedValue({ exigir_sesion: true, sesion: null });
    act(() => { window.dispatchEvent(new Event(api.EVENTO_SESION)); });
    expect(await screen.findByRole("heading", { name: /iniciar sesión en mediflow/i })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).toBeNull();
  });
});

describe("instalación con sesión obligatoria", () => {
  it("sin sesión solo se ve el ingreso; al ingresar se abre el inicio del rol de la cuenta", async () => {
    conSesion(null, true);
    const iniciar = vi.spyOn(api, "iniciarSesion").mockResolvedValue(ANA);
    render(<AppRouter rutaInicial="/documentos" />);
    expect(await screen.findByRole("heading", { name: /iniciar sesión en mediflow/i })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("link", { name: /seguir sin sesión/i })).toBeNull();
    const ingresar = screen.getByRole("button", { name: /ingresar/i });
    expect(ingresar).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Usuario"), "aud.ana");
    await userEvent.type(screen.getByLabelText("Clave"), "turno-noche-2026");
    await userEvent.click(ingresar);
    await waitFor(() => expect(iniciar).toHaveBeenCalledWith("aud.ana", "turno-noche-2026"));
    expect(await screen.findByTestId("sesion-activa")).toHaveTextContent("Ana Torres");
    expect(await screen.findByRole("heading", { level: 1, name: /cola de revisión/i })).toBeInTheDocument();
  });

  it("con credenciales malas avisa, borra la clave y no entra", async () => {
    conSesion(null, true);
    vi.spyOn(api, "iniciarSesion").mockRejectedValue(new api.ErrorApi(401, "Usuario o clave incorrectos"));
    render(<AppRouter rutaInicial="/documentos" />);
    await userEvent.type(await screen.findByLabelText("Usuario"), "aud.ana");
    await userEvent.type(screen.getByLabelText("Clave"), "equivocada");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Usuario o clave incorrectos");
    expect(screen.getByLabelText("Clave")).toHaveValue("");
    expect(screen.queryByTestId("sesion-activa")).toBeNull();
  });
});

describe("Administración: clave de las cuentas", () => {
  it("muestra qué cuentas tienen clave y permite definirla", async () => {
    const definir = vi.spyOn(api, "definirClave").mockResolvedValue({ ...USUARIOS[1], con_clave: true } as never);
    render(<AppRouter rutaInicial="/administracion" rolInicial="administrador" />);
    const filas = await screen.findAllByTestId("fila-usuario");
    expect(filas[0]).toHaveTextContent(/con clave/i);
    expect(filas[1]).toHaveTextContent(/sin clave/i);
    await userEvent.type(screen.getByLabelText(/firmo como/i), "admin.root");
    await userEvent.click(within(filas[1]).getByRole("button", { name: /definir la clave de qf\.maria/i }));
    const formulario = screen.getByTestId("cambio-de-clave");
    const guardar = within(formulario).getByRole("button", { name: /guardar clave/i });
    await userEvent.type(within(formulario).getByLabelText(/clave nueva de qf\.maria/i), "corta");
    expect(guardar).toBeDisabled();
    await userEvent.type(within(formulario).getByLabelText(/clave nueva de qf\.maria/i), "-pero-ya-no");
    await userEvent.click(guardar);
    await waitFor(() => expect(definir).toHaveBeenCalledWith("qf.maria", "corta-pero-ya-no", "admin.root"));
    expect(await screen.findByText(/sus sesiones abiertas se cerraron/i)).toBeInTheDocument();
  });
});


describe("producto: primer administrador y clave inicial", () => {
  it("sin cuentas, la pantalla de ingreso crea el primer administrador y entra con él (RN-S3)", async () => {
    vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: true, sesion: null, sin_cuentas: true, nombre_sede: "Sede Norte" });
    const crear = vi.spyOn(api, "crearPrimerAdministrador").mockResolvedValue({ usuario: "admin", nombre: "TI", rol: "administrador", debe_cambiar_clave: false });
    render(<AppRouter rutaInicial="/" />);
    const formulario = await screen.findByTestId("primer-administrador");
    await userEvent.type(within(formulario).getByLabelText(/^usuario/i), "admin");
    await userEvent.type(within(formulario).getByLabelText(/^nombre/i), "TI");
    await userEvent.type(within(formulario).getByLabelText(/^clave$/i), "Clave.inicial.2026");
    await userEvent.type(within(formulario).getByLabelText(/confirmar clave/i), "Clave.inicial.2026");
    await userEvent.click(within(formulario).getByRole("button", { name: /crear la cuenta de administrador/i }));
    await waitFor(() => expect(crear).toHaveBeenCalledWith("admin", "TI", "Clave.inicial.2026"));
    expect(await screen.findByTestId("sesion-activa")).toHaveTextContent("TI");
    expect(await screen.findByRole("heading", { level: 1, name: /administración/i })).toBeInTheDocument();
  });

  it("si la confirmación no coincide no llama a la API", async () => {
    vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: true, sesion: null, sin_cuentas: true });
    const crear = vi.spyOn(api, "crearPrimerAdministrador").mockResolvedValue(ADMIN);
    render(<AppRouter rutaInicial="/" />);
    const formulario = await screen.findByTestId("primer-administrador");
    await userEvent.type(within(formulario).getByLabelText(/^usuario/i), "admin");
    await userEvent.type(within(formulario).getByLabelText(/^nombre/i), "TI");
    await userEvent.type(within(formulario).getByLabelText(/^clave$/i), "Clave.inicial.2026");
    await userEvent.type(within(formulario).getByLabelText(/confirmar clave/i), "otra.cosa.2026");
    await userEvent.click(within(formulario).getByRole("button", { name: /crear la cuenta/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no coincide/i);
    expect(crear).not.toHaveBeenCalled();
  });

  it("una clave puesta por otra persona se cambia antes de ver nada", async () => {
    vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: true, sesion: { ...ANA, debe_cambiar_clave: true } });
    const cambiar = vi.spyOn(api, "cambiarMiClave").mockResolvedValue({ ...ANA, debe_cambiar_clave: false });
    render(<AppRouter rutaInicial="/revision" />);
    const pantalla = await screen.findByTestId("cambiar-clave");
    expect(screen.queryByRole("navigation", { name: /principal/i })).toBeNull();  // nada más a la vista
    await userEvent.type(within(pantalla).getByLabelText(/clave actual/i), "turno-noche-2026");
    await userEvent.type(within(pantalla).getByLabelText(/^clave nueva/i), "Nueva.clave.2026");
    await userEvent.type(within(pantalla).getByLabelText(/confirmar clave nueva/i), "Nueva.clave.2026");
    await userEvent.click(within(pantalla).getByRole("button", { name: /guardar clave/i }));
    await waitFor(() => expect(cambiar).toHaveBeenCalledWith("turno-noche-2026", "Nueva.clave.2026"));
    expect(await screen.findByRole("heading", { level: 1, name: /cola de revisión/i })).toBeInTheDocument();
  });

  it("con sesión se puede cambiar la clave desde la barra lateral, y en producto no se ofrece la demostración", async () => {
    vi.spyOn(api, "estadoSesion").mockResolvedValue({ exigir_sesion: true, sesion: ANA, nombre_sede: "Sede Norte" });
    render(<AppRouter rutaInicial="/revision" />);
    await screen.findByTestId("sesion-activa");
    expect(screen.getByRole("link", { name: /cambiar mi clave/i })).toHaveAttribute("href", "/cambiar-clave");
    expect(screen.queryByRole("link", { name: /modo demostración/i })).toBeNull();
    expect(screen.getByText(/Sede Norte/)).toBeInTheDocument();
  });
});
