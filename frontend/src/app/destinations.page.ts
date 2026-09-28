import { Component, inject, OnInit, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { Api } from "./api";
import { Destination, DestinationInput, RoutingRule, RoutingRuleInput, TYPES, SPECIALTIES, label } from "./models";

@Component({
  selector: "app-destinations",
  imports: [FormsModule, RouterLink],
  template: `
    <div class="page-heading"><div><h1>DESTINOS DE TRIAJE</h1>
      <p class="subtitle">Departamentos, colas y sistemas que reciben una asignación lógica. La entrega externa aún no está integrada.</p>
    </div></div>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
    <section class="panel catalog-panel">
      <div class="panel-heading"><div><h2>Destinos</h2><p class="muted">El código es estable; los destinos con reglas o historial se desactivan después de reasignar sus reglas.</p></div></div>
      <form class="catalog-form" (ngSubmit)="createDestination()">
        <input name="code" [(ngModel)]="draft.code" placeholder="CÓDIGO_NUEVO" required pattern="[A-Z][A-Z0-9_]{2,59}" aria-label="Código del destino" />
        <input name="name" [(ngModel)]="draft.name" placeholder="Nombre del destino" required aria-label="Nombre del destino" />
        <select name="kind" [(ngModel)]="draft.kind" aria-label="Tipo de destino">
          <option value="DEPARTMENT">Departamento</option><option value="QUEUE">Cola</option><option value="SYSTEM">Sistema</option>
        </select>
        <button class="primary" [disabled]="busy()">Crear destino</button>
      </form>
      <div class="table-scroll"><table><thead><tr><th>Destino</th><th>Tipo</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
        @for (item of destinations(); track item.code) {
          <tr><td>
            @if (editing() === item.code) {
              <input [name]="'name-' + item.code" [(ngModel)]="editName" aria-label="Nuevo nombre del destino" />
            } @else { <strong>{{ item.name }}</strong> }
            <small class="catalog-code">{{ item.code }}</small></td>
            <td>@if (editing() === item.code) {
              <select [name]="'kind-' + item.code" [(ngModel)]="editKind" aria-label="Nuevo tipo de destino">
                <option value="DEPARTMENT">Departamento</option><option value="QUEUE">Cola</option><option value="SYSTEM">Sistema</option>
              </select>
            } @else { {{ kindLabel(item.kind) }} }</td><td>{{ item.active ? "Activo" : "Inactivo" }}</td>
            <td>@if (editing() === item.code) {
                <button class="primary" [disabled]="busy() || !editName.trim()" (click)="saveEdit(item)">Guardar</button>
                <button class="secondary" (click)="editing.set(null)">Cancelar</button>
              } @else {
                <a class="secondary" [routerLink]="['/destinations', item.code, 'documents']">Abrir bandeja</a>
                <button class="secondary" [disabled]="busy()" (click)="startEdit(item)">Editar</button>
                <button class="secondary" [disabled]="busy() || item.code === 'COLA_URGENCIAS_MEDICAS'" (click)="toggle(item)">{{ item.active ? "Desactivar" : "Activar" }}</button>
                <button class="danger" [disabled]="busy() || item.code === 'COLA_URGENCIAS_MEDICAS'" (click)="deleteDestination(item)">Eliminar</button>
              }</td></tr>
        }
      </tbody></table></div>
    </section>
    <section class="panel catalog-panel">
      <div class="panel-heading"><div><h2>Reglas de asignación</h2>
        <p class="muted">Una coincidencia de especialidad prevalece sobre «Cualquiera». La prioridad urgente explícita siempre va a Urgencias Médicas.</p></div></div>
      <form class="catalog-form" (ngSubmit)="createRule()">
        <select name="document_type" [(ngModel)]="ruleDraft.document_type" aria-label="Tipo documental">
          @for (type of types; track type) { <option [value]="type">{{ label(type) }}</option> }
        </select>
        <select name="specialty" [(ngModel)]="ruleDraft.specialty" aria-label="Especialidad">
          <option value="ANY">Cualquiera</option>
          @for (specialty of specialties; track specialty) { <option [value]="specialty">{{ label(specialty) }}</option> }
        </select>
        <select name="destination_code" [(ngModel)]="ruleDraft.destination_code" aria-label="Destino" required>
          <option value="">Selecciona un destino</option>
          @for (item of destinations(); track item.code) { @if (item.active) { <option [value]="item.code">{{ item.name }}</option> } }
        </select>
        <button class="primary" [disabled]="busy()">Crear regla</button>
      </form>
      <div class="table-scroll"><table><thead><tr><th>Documento</th><th>Especialidad</th><th>Destino</th><th>Acciones</th></tr></thead><tbody>
        @for (rule of rules(); track rule.id) {
          <tr><td>{{ label(rule.document_type) }}</td><td>{{ rule.specialty === 'ANY' ? 'Cualquiera' : label(rule.specialty) }}</td>
            <td><select [ngModel]="rule.destination_code" [name]="'rule-' + rule.id" [attr.aria-label]="'Destino para ' + label(rule.document_type)" [disabled]="busy()" (ngModelChange)="changeRule(rule, $event)">
              @for (item of destinations(); track item.code) { @if (item.active || item.code === rule.destination_code) { <option [value]="item.code">{{ item.name }}</option> } }
            </select></td>
            <td><button class="secondary" [disabled]="busy()" (click)="toggleRule(rule)">{{ rule.active ? 'Desactivar' : 'Activar' }}</button>
              <button class="danger" [disabled]="busy()" (click)="deleteRule(rule)">Eliminar</button></td></tr>
        }
      </tbody></table></div>
    </section>
  `,
})
export class DestinationsPage implements OnInit {
  api = inject(Api);
  destinations = signal<Destination[]>([]);
  rules = signal<RoutingRule[]>([]);
  busy = signal(false);
  error = signal("");
  message = signal("");
  editing = signal<string | null>(null);
  editName = "";
  editKind: DestinationInput["kind"] = "DEPARTMENT";
  types = TYPES.filter((type) => !["OTHER", "UNKNOWN"].includes(type));
  specialties = SPECIALTIES.filter((specialty) => !["OTHER", "UNKNOWN"].includes(specialty));
  label = label;
  draft: DestinationInput = { code: "", name: "", kind: "DEPARTMENT" };
  ruleDraft: RoutingRuleInput = { document_type: "ECHOCARDIOGRAM_REPORT", specialty: "ANY", destination_code: "", active: true };
  ngOnInit() { void this.load(); }
  async load() {
    try {
      const [destinations, rules] = await Promise.all([this.api.destinations(), this.api.rules()]);
      this.destinations.set(destinations); this.rules.set(rules);
    } catch (error) { this.error.set((error as Error).message); }
  }
  kindLabel(kind: string) { return { DEPARTMENT: "Departamento", QUEUE: "Cola", SYSTEM: "Sistema" }[kind] || kind; }
  async run(action: () => Promise<unknown>) {
    this.busy.set(true); this.error.set(""); this.message.set("");
    try { await action(); await this.load(); this.message.set("Cambios guardados."); }
    catch (error) { this.error.set((error as Error).message); }
    finally { this.busy.set(false); }
  }
  createDestination() {
    const payload = { ...this.draft, code: this.draft.code.trim().toUpperCase(), name: this.draft.name.trim() };
    void this.run(async () => { await this.api.createDestination(payload); this.draft = { code: "", name: "", kind: "DEPARTMENT" }; });
  }
  startEdit(item: Destination) { this.editing.set(item.code); this.editName = item.name; this.editKind = item.kind; }
  saveEdit(item: Destination) {
    const name = this.editName.trim();
    const kind = this.editKind;
    void this.run(async () => { await this.api.updateDestination(item.code, { name, kind }); this.editing.set(null); });
  }
  toggle(item: Destination) { void this.run(() => this.api.updateDestination(item.code, { active: !item.active })); }
  deleteDestination(item: Destination) {
    if (confirm(`¿Eliminar el destino «${item.name}»?`)) void this.run(() => this.api.deleteDestination(item.code));
  }
  createRule() { void this.run(() => this.api.createRule({ ...this.ruleDraft })); }
  changeRule(rule: RoutingRule, destination_code: string) {
    void this.run(() => this.api.updateRule(rule.id, { destination_code }));
  }
  toggleRule(rule: RoutingRule) { void this.run(() => this.api.updateRule(rule.id, { active: !rule.active })); }
  deleteRule(rule: RoutingRule) {
    if (confirm(`¿Eliminar la regla de ${this.label(rule.document_type)}?`)) void this.run(() => this.api.deleteRule(rule.id));
  }
}
