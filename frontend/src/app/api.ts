import { Injectable, signal } from "@angular/core";
import { DocumentRecord, Result, StateEvent, ReviewAudit, label } from "./models";
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(
      typeof detail === "string"
        ? detail.startsWith("REVIEW_HAS_UNRESOLVED_ISSUES:")
          ? "La revisión conserva inconsistencias. Comprueba los campos y sus citas antes de resolver."
          : label(detail)
        : ((detail as { message?: string })?.message ?? "No se pudo completar la solicitud."),
    );
  }
}
@Injectable({ providedIn: "root" })
export class Api {
  config = signal({
    default_country: "EC",
    timezone: "America/Guayaquil",
    max_upload_bytes: 10485760,
  });
  async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch("/api" + path, { cache: "no-store", ...init });
    } catch {
      throw new Error("No hay conexión con la API. Comprueba los contenedores e intenta de nuevo.");
    }
    const data = await response.json().catch(() => null);
    if (!response.ok)
      throw new ApiError(
        response.status,
        data?.detail ?? "Servicio no disponible. Intenta de nuevo.",
      );
    return data as T;
  }
  async configure() {
    this.config.set(await this.request("/config"));
  }
  list(status: string, q: string, offset: number) {
    return this.request<{
      items: DocumentRecord[];
      total: number;
      limit: number;
      offset: number;
    }>(
      `/documents?limit=20&offset=${offset}&q=${encodeURIComponent(q)}${status ? "&status=" + encodeURIComponent(status) : ""}`,
    );
  }
  get(id: string) {
    return this.request<DocumentRecord>(`/documents/${id}`);
  }
  result(id: string) {
    return this.request<Result>(`/documents/${id}/result`);
  }
  history(id: string) {
    return this.request<StateEvent[]>(`/documents/${id}/history`);
  }
  reviews(id: string) {
    return this.request<ReviewAudit[]>(`/documents/${id}/reviews`);
  }
  upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.request<DocumentRecord>("/documents", {
      method: "POST",
      body: form,
    });
  }
  process(id: string) {
    return this.request<Result>(`/documents/${id}/process`, { method: "POST" });
  }
  review(id: string, body: unknown) {
    return this.request<Result>(`/documents/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  async preview(id: string, page: number) {
    const response = await fetch(`/api/documents/${id}/preview?page=${page}`, {
      cache: "no-store",
    });
    if (!response.ok)
      throw new Error("No se pudo mostrar esta página. Puedes descargar el PDF original.");
    return {
      blob: await response.blob(),
      pages: Number(response.headers.get("X-Page-Count") || 1),
    };
  }
  async original(id: string): Promise<Blob> {
    const r = await fetch(`/api/documents/${id}/file`, { cache: "no-store" });
    if (!r.ok) throw new Error("No se pudo abrir el original. Intenta de nuevo.");
    return r.blob();
  }
}
