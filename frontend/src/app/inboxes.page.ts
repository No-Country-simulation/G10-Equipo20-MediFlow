import { Component, effect, inject, signal, untracked } from "@angular/core";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { DatePipe } from "@angular/common";
import { Api } from "./api";
import { Destination, DocumentRecord, label } from "./models";

@Component({
  selector: "app-inboxes",
  imports: [RouterLink, DatePipe],
  template: `
    <div class="page-heading"><div><h1>BANDEJAS LOCALES</h1>
      <p class="subtitle">Documentos asignados al destino en {{ api.country() }}.</p>
    </div></div>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    <section class="panel catalog-panel">
      <div class="panel-heading"><h2>Destinos</h2></div>
      <div class="inbox-links">
        @for (item of destinations(); track item.code) {
          <a [routerLink]="['/destinations', item.code, 'documents']" [class.active]="item.code === code()">
            {{ item.name }}
          </a>
        }
      </div>
    </section>
    @if (code()) {
      <section class="panel catalog-panel">
        <div class="panel-heading"><div><h2>{{ destinationName() }}</h2>
          <p class="muted">Entregado a bandeja local no significa recibido por una HCE ni otro sistema externo.</p></div>
        </div>
        @if (loading()) { <p class="muted">Cargando documentos…</p> }
        @else if (!documents().length) { <p class="muted">No hay documentos para este destino y país.</p> }
        @else { <div class="table-scroll"><table><thead><tr><th>Documento</th><th>Estado</th><th>Recibido</th></tr></thead><tbody>
          @for (doc of documents(); track doc.document_id) {
            <tr><td><a [routerLink]="['/documents', doc.document_id]">{{ doc.original_filename }}</a></td>
              <td>{{ label(doc.status) }}</td><td>{{ doc.received_at | date:'dd/MM/yyyy, HH:mm' }}</td></tr>
          }
        </tbody></table></div> }
        <p class="muted">{{ total() }} documento(s)</p>
        <div><button class="secondary" (click)="page(-1)" [disabled]="offset() === 0">Anterior</button>
          <button class="secondary" (click)="page(1)" [disabled]="offset() + 20 >= total()">Siguiente</button></div>
      </section>
    }
  `,
})
export class InboxesPage {
  api = inject(Api);
  route = inject(ActivatedRoute);
  destinations = signal<Destination[]>([]);
  documents = signal<DocumentRecord[]>([]);
  code = signal("");
  total = signal(0);
  offset = signal(0);
  loading = signal(false);
  error = signal("");
  label = label;
  private sequence = 0;
  constructor() {
    this.route.paramMap.subscribe(params => { this.code.set(params.get("code") || ""); this.offset.set(0); });
    effect(() => { this.api.country(); this.code(); untracked(() => void this.load()); });
    void this.api.destinations().then(items => this.destinations.set(items)).catch(e => this.error.set(e.message));
  }
  destinationName() { return this.destinations().find(item => item.code === this.code())?.name || this.code(); }
  async load() {
    if (!this.code()) { this.documents.set([]); return; }
    const seq = ++this.sequence;
    this.loading.set(true); this.error.set("");
    try {
      const result = await this.api.list("", "", this.offset(), this.code());
      if (seq === this.sequence) { this.documents.set(result.items); this.total.set(result.total); }
    } catch (e) { if (seq === this.sequence) this.error.set((e as Error).message); }
    finally { if (seq === this.sequence) this.loading.set(false); }
  }
  page(direction: number) { this.offset.update(n => Math.max(0, n + direction * 20)); void this.load(); }
}
