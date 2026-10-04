import { Component, effect, inject, signal, untracked } from "@angular/core";
import { RouterLink } from "@angular/router";
import { Api } from "./api";
import { DocumentSummary, STATUSES, label } from "./models";

@Component({
  selector: "app-home", imports: [RouterLink],
  template: `
    <div class="page-heading"><div><p class="eyebrow">PANEL OPERATIVO · {{ api.country() }}</p>
      <h1>Tu operación, de un vistazo</h1><p class="subtitle">Documentos, revisión y entrega en las bandejas locales.</p></div>
      @if (api.can('DOCUMENTS_UPLOAD')) { <a class="primary" routerLink="/documents">＋ Cargar documento</a> }</div>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (loading()) { <p class="muted" role="status">Actualizando indicadores…</p> }
    @if (summary(); as s) {
      <div class="metric-grid">
        <a class="metric-card" routerLink="/documents"><span>Documentos recibidos</span><strong>{{ s.total }}</strong><small>En {{ countryName() }}</small></a>
        <a class="metric-card" routerLink="/review"><span>Revisión humana</span><strong>{{ s.pending_review }}</strong><small>Casos pendientes de resolver</small></a>
        <a class="metric-card" routerLink="/inboxes"><span>Entregados localmente</span><strong>{{ s.delivered_local }}</strong><small>Disponibles en sus bandejas</small></a>
        <div class="metric-card"><span>Prioridad explícita alta</span><strong>{{ (s.by_priority['URGENT'] || 0) + (s.by_priority['CRITICAL'] || 0) }}</strong><small>Declarada urgente o crítica</small></div>
      </div>
      <div class="overview-grid">
        <section class="panel"><div class="panel-heading"><h2>Flujo documental</h2><span class="section-number">ESTADO ACTUAL</span></div>
          <div class="status-distribution">
            @for (state of statuses; track state) {
              <div class="distribution-row"><span>{{ label(state) }}</span><div class="distribution-track"><div [style.width.%]="s.total ? (s.by_status[state] || 0) / s.total * 100 : 0"></div></div><strong>{{ s.by_status[state] || 0 }}</strong></div>
            }
          </div>
        </section>
        <section class="panel"><div class="panel-heading"><h2>Prioridad documental</h2></div>
          <div class="priority-list">@for (level of priorities; track level) {
            <div><span class="badge" [attr.data-priority]="level">{{ label(level) }}</span><strong>{{ s.by_priority[level] || 0 }}</strong></div>
          }</div><p class="panel-note">Prioridad basada en texto explícito. Los documentos sin análisis figuran como «Sin evaluar».</p>
          <a class="workflow-link" routerLink="/review"><strong>Abrir revisión humana →</strong><small>Contrasta la extracción con el original y conserva la auditoría.</small></a>
        </section>
      </div>
      @if (!s.total) { <section class="empty"><h2>Empieza con tu primer documento</h2><p>No hay documentos en {{ countryName() }}. Carga un PDF o imagen para iniciar el flujo.</p></section> }
    }
  `,
})
export class HomePage {
  api = inject(Api);
  summary = signal<DocumentSummary | null>(null);
  loading = signal(false); error = signal("");
  statuses = STATUSES; priorities = ["ROUTINE", "URGENT", "CRITICAL", "UNASSESSED"]; label = label;
  private sequence = 0;
  constructor() { effect(() => { this.api.country(); untracked(() => void this.load()); }); }
  countryName() { return this.api.countries().find(item => item.code === this.api.country())?.name || this.api.country(); }
  async load() {
    const seq = ++this.sequence; this.loading.set(true); this.error.set(""); this.summary.set(null);
    try { const data = await this.api.summary(); if (seq === this.sequence) this.summary.set(data); }
    catch (e) { if (seq === this.sequence) this.error.set((e as Error).message); }
    finally { if (seq === this.sequence) this.loading.set(false); }
  }
}
