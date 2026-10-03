import { afterEach, describe, expect, it, vi } from "vitest";

import { colaRevision, confirmarEntrega, enviarDocumento, resolverRevision } from "./api";
import { detalleCaso1 } from "./test/fixtures";

function respuesta(cuerpo: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, statusText: "x", json: () => Promise.resolve(cuerpo) } as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("cliente de la API", () => {
  it("envía el documento como JSON a /api/documentos y devuelve el detalle", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respuesta(detalleCaso1()));
    const detalle = await enviarDocumento({ documento_id: "DOC-CLIN-2026-8942", canal_origen: "Guardia_Emergencias", tipo_contenido: "texto", contenido_texto: "TC..." });
    expect(fetchMock).toHaveBeenCalledWith("/api/documentos", expect.objectContaining({ method: "POST" }));
    const cuerpo = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(cuerpo.canal_origen).toBe("Guardia_Emergencias");
    expect(detalle.resultado?.clasificacion.nivel_prioridad).toBe("Crítico");
  });

  it("un rechazo 400 devuelve el cuerpo con codigo_error en vez de lanzar (RN-A1, RN-O5)", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(respuesta({ documento_id: "X", estado: "RECHAZADO", codigo_error: "tamano_excedido" }, 400));
    const detalle = await enviarDocumento({ documento_id: "X", canal_origen: "Externo", tipo_contenido: "texto", contenido_texto: "x" });
    expect(detalle.codigo_error).toBe("tamano_excedido");
  });

  it("un error 409 lanza ErrorApi con el detalle del backend", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(respuesta({ detail: "RN-I4: no está en revisión" }, 409));
    await expect(resolverRevision("DOC-1", { accion: "aprobar", motivo: "x" })).rejects.toMatchObject({ status: 409, detalle: "RN-I4: no está en revisión" });
  });

  it("consulta la cola y confirma entregas en las rutas correctas", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respuesta([]));
    await colaRevision();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/revision", expect.anything());
    fetchMock.mockReturnValue(respuesta({ documento_id: "DOC-1", estado: "ENRUTADO", entregas: {}, retenidas: {}, pendientes: [] }));
    await confirmarEntrega("DOC-1", "Cola_Emergencia_Medica");
    expect(fetchMock).toHaveBeenLastCalledWith("/api/documentos/DOC-1/entregar", expect.objectContaining({ method: "POST" }));
  });
});

describe("archivos, listado y original (mejora de la rama bryan-segovia)", () => {
  it("envía el archivo como multipart con sus campos", async () => {
    const { enviarArchivo } = await import("./api");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respuesta(detalleCaso1()));
    const archivo = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "informe.pdf", { type: "application/pdf" });
    await enviarArchivo(archivo, { documento_id: "DOC-1", canal_origen: "Externo", cobertura_paciente: "contributivo" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/documentos/archivo");
    const form = (init as RequestInit).body as FormData;
    expect(form.get("documento_id")).toBe("DOC-1");
    expect(form.get("canal_origen")).toBe("Externo");
    expect(form.get("cobertura_paciente")).toBe("contributivo");
    expect((form.get("archivo") as File).name).toBe("informe.pdf");
  });

  it("construye las URLs del original y la vista previa", async () => {
    const { urlOriginal, urlVistaPrevia } = await import("./api");
    expect(urlOriginal("DOC 1")).toBe("/api/documentos/DOC%201/original");
    expect(urlVistaPrevia("DOC-1", 2)).toBe("/api/documentos/DOC-1/vista_previa?pagina=2");
  });

  it("lista documentos con filtros", async () => {
    const { listarDocumentos } = await import("./api");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respuesta({ items: [], total: 0, limit: 20, offset: 0 }));
    await listarDocumentos({ estado: "EN_REVISION_HUMANA", q: "DOC" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/documentos?estado=EN_REVISION_HUMANA&q=DOC");
  });
});
