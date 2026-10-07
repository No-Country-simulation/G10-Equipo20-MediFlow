import { Component, inject, signal, OnInit } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { Api } from "./api";
import { DocumentaryPolicy, label } from "./models";

@Component({selector: "app-policies", imports: [FormsModule], template: `
  <div class="page-heading"><div><p class="eyebrow">SUPERADMIN · CONFIGURACIÓN GLOBAL</p><h1>Reglas documentales</h1><p class="subtitle">Campos suficientes, pesos y umbral por categoría. Las citas siempre se comprueban.</p></div></div>
  @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
  @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
  <section class="panel"><div class="panel-heading"><h2>Configuración por tipo</h2></div>
    <label>Tipo documental<select [(ngModel)]="selected" (ngModelChange)="choose()">@for (p of policies(); track p.document_type) { <option [value]="p.document_type">{{ label(p.document_type) }} · v{{ p.version }}</option> }</select></label>
    @if (current) { <form (ngSubmit)="save()"><fieldset [disabled]="busy()">
      <label>Grupos requeridos<textarea name="groups" [(ngModel)]="groups" rows="7" required></textarea></label><small>Un grupo por línea; separa alternativas con coma. Usa nombres del catálogo.</small>
      <p class="muted">Campos disponibles: {{ allowedFields().join(', ') }}</p>
      <div class="policy-weights">@for (key of weightKeys; track key) { <label>{{ weightLabels[key] }}<input type="number" [name]="key" [(ngModel)]="weights[key]" min="0.001" max="1" step="0.01" required /></label> }</div>
      <label>Umbral automático (0–1)<input type="number" name="threshold" [(ngModel)]="threshold" min="0" max="1" step="0.01" required /></label>
      <p class="muted">Los pesos deben sumar 1. Indicador documental; no certeza clínica. Guardar crea una nueva versión para futuros análisis.</p>
      <button class="primary" type="submit">{{ busy() ? 'Guardando…' : 'Guardar nueva versión' }}</button>
    </fieldset></form> }
  </section>`})
export class PoliciesPage implements OnInit {
  api = inject(Api); policies = signal<DocumentaryPolicy[]>([]); error = signal(""); message = signal(""); busy = signal(false);
  selected = ""; current: DocumentaryPolicy | null = null; groups = ""; weights: Record<string,number> = {}; threshold = .85; label = label;
  weightKeys = ["readability", "completeness", "evidence", "consistency"];
  weightLabels: Record<string,string> = {readability:"Legibilidad", completeness:"Cobertura", evidence:"Evidencia", consistency:"Consistencia"};
  async ngOnInit() { try { await this.api.configure(); this.policies.set(await this.api.request<DocumentaryPolicy[]>("/admin/document-policies")); this.selected = this.policies()[0]?.document_type || ""; this.choose(); } catch(e) { this.error.set((e as Error).message); } }
  allowedFields() {return this.api.catalog().types.find(t => t.code === this.selected)?.fields || [];}
  choose() {this.current = this.policies().find(p => p.document_type === this.selected) || null; if(this.current) {this.groups = this.current.required_groups.map(g => g.join(", ")).join("\n"); this.weights = {...this.current.weights}; this.threshold = this.current.threshold;}}
  async save() {if(!this.current || this.busy()) return; this.busy.set(true); this.error.set(""); this.message.set(""); try {
    const p = await this.api.write<DocumentaryPolicy>(`/admin/document-policies/${this.selected}`, "PUT", {expected_version: this.current.version, required_groups: this.groups.split("\n").filter(g => g.trim()).map(g => g.split(",").map(n => n.trim())), weights:this.weights, threshold:this.threshold});
    this.policies.update(rows => rows.map(row => row.document_type === p.document_type ? p : row)); this.choose(); this.message.set("Nueva versión guardada. Los resultados anteriores conservan sus reglas.");
  } catch(e) {this.error.set((e as Error).message);} finally {this.busy.set(false);}}
}
