import { Injectable, signal } from "@angular/core";
import { DocumentRecord, Result, StateEvent, ReviewAudit, label, DocumentCatalog, DocumentSummary, registerCatalog } from "./models";
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(
      typeof detail === "string"
        ? detail.startsWith("PERMISSION_DENIED:") ? "Tu cuenta no tiene permiso para realizar esta acción." : detail.startsWith("REVIEW_HAS_UNRESOLVED_ISSUES:")
          ? "La revisión conserva inconsistencias. Comprueba los campos y sus citas antes de resolver."
          : label(detail)
        : ((detail as { message?: string })?.message ?? "No se pudo completar la solicitud."),
    );
  }
}
export interface AccountInfo {id: number; role: string; country: string | null; email: string; name?: string; permissions?: string[]; denied_permissions?: string[];}
@Injectable({ providedIn: "root" })
export class Api {
  account = signal<AccountInfo | null>(null);
  can(code: string) { const a = this.account(); return a?.role === "SUPERADMIN" || (!!a?.permissions?.includes(code) && !a?.denied_permissions?.includes(code)); }
  write<T = unknown>(path: string, method: string, body?: unknown) { return this.request<T>(path, {method, headers: {"Content-Type": "application/json"}, ...(body === undefined ? {} : {body: JSON.stringify(body)})}); }
  catalog = signal<DocumentCatalog>({types: [], specialties: [], rule_version: ""});
  countries = signal<{ code: string; name: string }[]>([]);
  country = signal(localStorage.getItem("mediflow-country") || "EC");
  private configuration?: Promise<void>;
  selectCountry(code: string) {
    this.country.set(code);
    localStorage.setItem("mediflow-country", code);
  }
  config = signal({
    default_country: "EC",
    timezone: "America/Guayaquil",
    max_upload_bytes: 10485760,
  });
  async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch("/api" + path, { cache: "no-store", credentials: "same-origin", ...init });
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
  async me() { const a = await this.request<AccountInfo>("/auth/me"); this.account.set(a); return a; }
  register(data: {country: string; identity_number: string; email: string; password: string}) {
    return this.request<{message: string}>("/auth/register", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  }
  patientLogin(data: {country: string; identity_number: string; password: string}) {
    return this.request<{role: string}>("/auth/patient-login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  }
  adminLogin(data: {email: string; password: string}) {
    return this.request<{role: string}>("/auth/admin-login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  }
  logout() { return this.request<{message: string}>("/auth/logout", {method: "POST"}); }
  myDocuments() { return this.request<DocumentRecord[]>("/auth/my-documents"); }
  configure(): Promise<void> {
    return this.configuration ??= (async () => {
      const [config, countries, catalog] = await Promise.all([
        this.request<{ default_country: string; timezone: string; max_upload_bytes: number }>("/config"),
        this.request<{ code: string; name: string }[]>("/countries"),
        this.request<DocumentCatalog>("/document-types"),
      ]);
      this.config.set(config);
      this.countries.set(countries);
      this.catalog.set(catalog);
      registerCatalog(catalog);
      if (!countries.some((item) => item.code === this.country()))
        this.selectCountry(config.default_country);
    })().catch((error) => { this.configuration = undefined; throw error; });
  }
  list(status: string, q: string, offset: number, destination = "", priority = "", filters: Record<string,string> = {}) {
    return this.request<{
      items: DocumentRecord[];
      total: number;
      limit: number;
      offset: number;
    }>(
      `/documents?limit=20&offset=${offset}&country=${encodeURIComponent(this.country())}&q=${encodeURIComponent(q)}${Object.entries(filters).filter(([,v]) => v !== "").map(([k,v]) => "&" + encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("")}${status ? "&status=" + encodeURIComponent(status) : ""}${destination ? "&destination=" + encodeURIComponent(destination) : ""}${priority ? "&priority=" + encodeURIComponent(priority) : ""}`,
    );
  }
  summary() {
    return this.request<DocumentSummary>(`/documents/summary?country=${encodeURIComponent(this.country())}`);
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
    form.append("country", this.country());
    return this.request<DocumentRecord>("/documents", {
      method: "POST",
      body: form,
    });
  }
  uploadText(text: string, origin_channel: string) {return this.write<DocumentRecord>("/documents/text", "POST", {text, origin_channel, country: this.country()});}
  enqueue(id: string) {return this.write<import("./models").ProcessingJob>(`/documents/${id}/processing-jobs`, "POST");}
  latestJob(id: string) {return this.request<import("./models").ProcessingJob>(`/documents/${id}/processing-jobs/latest`);}
  backups(id: string) {return this.request<import("./models").Backup[]>(`/documents/${id}/backups`);}
  retryBackups(id: string) {return this.write(`/documents/${id}/backups/retry`, "POST");}
  process(id: string) {
    return this.request<Result>(`/documents/${id}/process`, { method: "POST" });
  }
  triage(file: File) {
    const form = new FormData();
    form.append("file", file);
    form.append("country", this.country());
    return this.request<Result>("/documents/triage", { method: "POST", body: form });
  }
  deleteDocument(id: string) {
    return this.request<void>(`/documents/${id}`, { method: "DELETE" });
  }
  destinations() {
    return this.request<import("./models").Destination[]>("/destinations");
  }
  patients(q = "", offset = 0) {
    return this.request<{ items: import("./models").Patient[]; total: number; limit: number; offset: number }>(
      `/patients?country=${encodeURIComponent(this.country())}&q=${encodeURIComponent(q)}&limit=20&offset=${offset}`,
    );
  }
  patient(id: number) { return this.request<import("./models").Patient>(`/patients/${id}`); }
  patientDocuments(id: number) { return this.request<DocumentRecord[]>(`/patients/${id}/documents`); }
  updatePatient(id: number, body: { name?: string; age?: number | null; identity_number?: string }) {
    return this.request<import("./models").Patient>(`/patients/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  }
  createDestination(data: import("./models").DestinationInput) {
    return this.request<import("./models").Destination>("/destinations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
  }
  updateDestination(code: string, data: Partial<import("./models").Destination>) {
    return this.request<import("./models").Destination>(`/destinations/${code}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
  }
  deleteDestination(code: string) {
    return this.request<void>(`/destinations/${code}`, { method: "DELETE" });
  }
  rules() {
    return this.request<import("./models").RoutingRule[]>("/routing-rules");
  }
  createRule(data: import("./models").RoutingRuleInput) {
    return this.request<import("./models").RoutingRule>("/routing-rules", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
  }
  updateRule(id: number, data: Partial<import("./models").RoutingRule>) {
    return this.request<import("./models").RoutingRule>(`/routing-rules/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
  }
  deleteRule(id: number) {
    return this.request<void>(`/routing-rules/${id}`, { method: "DELETE" });
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
      credentials: "same-origin",
    });
    if (!response.ok)
      throw new Error("No se pudo mostrar esta página. Puedes descargar el PDF original.");
    return {
      blob: await response.blob(),
      pages: Number(response.headers.get("X-Page-Count") || 1),
    };
  }
  async original(id: string): Promise<Blob> {
    const r = await fetch(`/api/documents/${id}/file`, { cache: "no-store", credentials: "same-origin" });
    if (!r.ok) throw new Error("No se pudo abrir el original. Intenta de nuevo.");
    return r.blob();
  }
}
