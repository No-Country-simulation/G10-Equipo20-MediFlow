import { Component, effect, inject, signal, untracked } from "@angular/core";
import { RouterLink } from "@angular/router";
import { FormsModule } from "@angular/forms";
import { Api } from "./api";
import { Patient } from "./models";

@Component({
  selector: "app-patients",
  imports: [RouterLink, FormsModule],
  template: `
    <div class="page-heading"><div><h1>PACIENTES</h1>
      <p class="subtitle">Identificaciones extraídas con evidencia y formato válido para {{ api.country() }}. El formato no verifica la identidad civil.</p>
    </div></div>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    <section class="panel patients-panel">
      <div class="panel-heading"><h2>Directorio <span class="count">{{ total() }}</span></h2>
      <form (ngSubmit)="load(true)" class="directory-search">
        <input name="q" [(ngModel)]="search" placeholder="Buscar nombre o identificación" aria-label="Buscar pacientes" />
        <button class="secondary">Buscar</button>
      </form></div>
      @if (loading()) { <p class="muted">Cargando pacientes…</p> }
      @else if (!items().length) { <div class="empty"><span class="empty-icon">♙</span><h3>Sin pacientes identificados</h3><p>No hay pacientes identificados para este país.</p></div> }
      @else { <div class="table-scroll"><table><thead><tr><th>ID</th><th>Paciente</th><th>Identificación</th><th>Documentos</th></tr></thead><tbody>
        @for (patient of items(); track patient.id) {
          <tr><td>{{ patient.id }}</td><td><a [routerLink]="['/patients', patient.id]">{{ patient.name }}</a></td>
            <td>{{ patient.identity_type }} · {{ patient.identity_number }}</td><td>{{ patient.document_count }}</td></tr>
        }
      </tbody></table></div> }
      <div class="pagination"><span>{{ total() }} paciente(s)</span>
      <div><button class="secondary" (click)="page(-1)" [disabled]="offset() === 0">Anterior</button>
        <button class="secondary" (click)="page(1)" [disabled]="offset() + 20 >= total()">Siguiente</button></div></div>
    </section>
  `,
})
export class PatientsPage {
  api = inject(Api);
  items = signal<Patient[]>([]);
  total = signal(0);
  offset = signal(0);
  loading = signal(false);
  error = signal("");
  search = "";
  private sequence = 0;
  constructor() { effect(() => { this.api.country(); untracked(() => void this.load(true)); }); }
  async load(reset = false) {
    if (reset) this.offset.set(0);
    const seq = ++this.sequence;
    this.loading.set(true); this.error.set("");
    try { const data = await this.api.patients(this.search, this.offset());
      if (seq === this.sequence) { this.items.set(data.items); this.total.set(data.total); }
    } catch (e) { if (seq === this.sequence) this.error.set((e as Error).message); }
    finally { if (seq === this.sequence) this.loading.set(false); }
  }
  page(direction: number) { this.offset.update(n => Math.max(0, n + direction * 20)); void this.load(); }
}
