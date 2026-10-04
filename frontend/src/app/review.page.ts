import { Component, effect, inject, signal, untracked } from "@angular/core";
import { RouterLink } from "@angular/router";
import { DatePipe } from "@angular/common";
import { Api } from "./api";
import { DocumentRecord, Result, label } from "./models";

@Component({
  selector: "app-review-queue", imports: [RouterLink, DatePipe],
  template: `
    <div class="page-heading"><div><p class="eyebrow">INTERVENCIÓN HUMANA · {{ api.country() }}</p><h1>Revisión documental</h1>
      <p class="subtitle">Comprueba los casos ambiguos junto al documento original.</p></div><button class="secondary" (click)="load()" [disabled]="loading()">↻ Actualizar</button></div>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    <section class="panel"><div class="panel-heading"><h2>Pendientes <span class="count">{{ total() }}</span></h2></div>
      @if (loading()) { <div class="empty" role="status">Cargando casos…</div> }
      @else if (!items().length) { <div class="empty"><h3>No hay casos pendientes</h3><p>Todos los documentos de este país están fuera de la cola de revisión.</p></div> }
      @else { <div class="table-scroll"><table><thead><tr><th>Documento</th><th>Prioridad</th><th>Motivos de revisión</th><th>Recibido</th><th></th></tr></thead><tbody>
        @for (doc of items(); track doc.document_id) {
          <tr><td><a [routerLink]="['/review', doc.document_id]" [queryParams]="{offset: offset()}"><strong>{{ doc.original_filename }}</strong></a>
            <small class="catalog-code">{{ label(results()[doc.document_id]?.classification?.document_type || 'UNKNOWN') }}</small></td>
            <td><span class="badge" [attr.data-priority]="results()[doc.document_id]?.priority?.level">{{ label(results()[doc.document_id]?.priority?.level || 'UNASSESSED') }}</span></td>
            <td><ul class="review-reasons">@for (issue of reasons(doc.document_id); track $index) { <li>{{ label(issue) }}</li> }</ul></td>
            <td>{{ doc.received_at | date:'dd/MM/yyyy, HH:mm':'-0500' }}</td>
            <td><a class="secondary" [routerLink]="['/review', doc.document_id]" [queryParams]="{offset: offset()}">Revisar →</a></td></tr>
        }
      </tbody></table></div> }
      <div class="pagination"><span>{{ total() }} caso(s)</span><div><button class="secondary" (click)="page(-1)" [disabled]="loading() || offset() === 0">Anterior</button>
        <button class="secondary" (click)="page(1)" [disabled]="loading() || offset() + 20 >= total()">Siguiente</button></div></div>
    </section>
  `,
})
export class ReviewPage {
  api = inject(Api); items = signal<DocumentRecord[]>([]); results = signal<Record<string, Result | null>>({});
  total = signal(0); offset = signal(0); loading = signal(false); error = signal(""); label = label;
  private sequence = 0;
  constructor() { effect(() => { this.api.country(); untracked(() => { this.offset.set(0); void this.load(); }); }); }
  reasons(id: string) { const r = this.results()[id]; return r?.validation?.issues.length ? r.validation.issues : [r?.error_code || "Revisar el original y la extracción"]; }
  async load() {
    const seq = ++this.sequence; this.loading.set(true); this.error.set("");
    try {
      const data = await this.api.list("EN_REVISION_HUMANA", "", this.offset());
      const results = await Promise.all(data.items.map(async doc => [doc.document_id, await this.api.result(doc.document_id)] as const));
      if (seq === this.sequence) { this.items.set(data.items); this.total.set(data.total); this.results.set(Object.fromEntries(results)); }
    } catch (e) { if (seq === this.sequence) { this.items.set([]); this.error.set((e as Error).message); } }
    finally { if (seq === this.sequence) this.loading.set(false); }
  }
  page(direction: number) { this.offset.update(n => Math.max(0, n + direction * 20)); void this.load(); }
}
