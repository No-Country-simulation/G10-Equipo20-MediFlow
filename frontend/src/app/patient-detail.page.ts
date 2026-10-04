import { Component, inject, signal } from "@angular/core";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { FormsModule } from "@angular/forms";
import { DatePipe } from "@angular/common";
import { Api } from "./api";
import { DocumentRecord, Patient, label } from "./models";

@Component({
  selector: "app-patient-detail",
  imports: [RouterLink, FormsModule, DatePipe],
  template: `
    <a routerLink="/patients" class="back-link">← Volver a pacientes</a>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
    @if (patient(); as p) {
      <div class="page-heading"><div><h1>{{ p.name }}</h1>
        <p class="subtitle">Paciente #{{ p.id }} · {{ p.country }} · {{ p.identity_type }} {{ p.identity_number }}</p>
      </div></div>
      <section class="panel catalog-panel"><div class="panel-heading"><h2>Datos básicos</h2></div>
        <p class="muted">La coincidencia de formato no verifica la identidad civil. Corrige aquí los datos confirmados con el original.</p>
        <form (ngSubmit)="save()" class="catalog-form">
          <label>Nombre <input name="name" [(ngModel)]="name" required /></label>
          <label>Edad <input name="age" type="number" min="0" max="130" [(ngModel)]="age" /></label>
          <label>Identificación <input name="identity" [(ngModel)]="identity" required /></label>
          <button class="primary" [disabled]="busy() || !api.can('PATIENTS_EDIT')">Guardar cambios</button>
        </form>
      </section>
      <section class="panel catalog-panel"><div class="panel-heading"><h2>Documentos asociados</h2></div>
        @if (!documents().length) { <p class="muted">No hay documentos asociados.</p> }
        @else { <div class="table-scroll"><table><thead><tr><th>Documento</th><th>Estado</th><th>Recibido</th></tr></thead><tbody>
          @for (doc of documents(); track doc.document_id) {
            <tr><td><a [routerLink]="['/documents', doc.document_id]">{{ doc.original_filename }}</a></td>
              <td>{{ label(doc.status) }}</td><td>{{ doc.received_at | date:'dd/MM/yyyy, HH:mm' }}</td></tr>
          }
        </tbody></table></div> }
      </section>
    }
  `,
})
export class PatientDetailPage {
  api = inject(Api);
  id = Number(inject(ActivatedRoute).snapshot.paramMap.get("id"));
  patient = signal<Patient | null>(null);
  documents = signal<DocumentRecord[]>([]);
  busy = signal(false);
  error = signal("");
  message = signal("");
  name = "";
  identity = "";
  age: number | null = null;
  label = label;
  constructor() { void this.load(); }
  async load() {
    try {
      const [patient, docs] = await Promise.all([this.api.patient(this.id), this.api.patientDocuments(this.id)]);
      this.patient.set(patient); this.documents.set(docs);
      this.name = patient.name; this.identity = patient.identity_number; this.age = patient.age;
    } catch (e) { this.error.set((e as Error).message); }
  }
  async save() {
    this.busy.set(true); this.error.set(""); this.message.set("");
    try {
      const patient = await this.api.updatePatient(this.id, { name: this.name.trim(), age: this.age,
        identity_number: this.identity.trim() });
      this.patient.set(patient); this.message.set("Datos guardados y cambio registrado en auditoría.");
    } catch (e) { this.error.set((e as Error).message); }
    finally { this.busy.set(false); }
  }
}
