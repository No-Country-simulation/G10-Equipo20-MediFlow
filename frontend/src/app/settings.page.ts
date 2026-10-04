import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';
interface Variable { name: string; value: string | null; secret: boolean; configured: boolean; edit?: string; }
@Component({selector: 'app-settings', imports: [FormsModule], template: `
  <div class="page-heading"><div><p class="eyebrow">SUPERADMIN</p><h1>Variables de Configuración</h1>
  <p class="subtitle">Claves y proveedor de los próximos análisis. Los resultados anteriores se conservan.</p></div></div>
  @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
  @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
  <section class="panel admin-panel"><p class="muted">USAR_GEMINI activo: Gemini. Desactivado: OpenAI. Las claves guardadas nunca se muestran; escribe una nueva para reemplazarlas.</p>
  <div class="table-scroll"><table><thead><tr><th>Name</th><th>Value</th><th>Acciones</th></tr></thead><tbody>
  @for (v of items(); track v.name) { <tr><td class="mono">{{ v.name }}</td><td>
    @if (v.name === 'USAR_GEMINI') { <label class="check-option"><input type="checkbox" [checked]="v.edit === 'true'" (change)="v.edit = $any($event.target).checked ? 'true' : 'false'" /> Usar Gemini</label> }
    @else { <input [type]="v.secret ? 'password' : 'text'" [(ngModel)]="v.edit" [attr.aria-label]="v.name" [placeholder]="v.secret ? (v.configured ? 'Clave configurada · reemplazar' : 'Sin configurar') : ''" autocomplete="off" /> }
  </td><td><button class="secondary" (click)="save(v)" [disabled]="busy() || (v.secret && !v.edit)">Guardar</button>
    @if (!reserved.includes(v.name)) { <button class="danger" (click)="remove(v)" [disabled]="busy()">Eliminar</button> }
  </td></tr> }</tbody></table></div>
  <form class="admin-form" (ngSubmit)="create()"><h2>Agregar variable</h2><label>Name<input name="name" [(ngModel)]="name" pattern="[A-Z][A-Z0-9_]{0,99}" required placeholder="NOMBRE_EN_MAYUSCULAS" /></label>
  <label>Value<input name="value" [(ngModel)]="value" type="password" autocomplete="off" /></label><button class="primary" [disabled]="busy()">Crear</button></form>
  <p class="muted">Las variables personalizadas se guardan como configuración; solo las claves y modelos indicados arriba controlan el proveedor actualmente.</p></section>`})
export class SettingsPage {
  api = inject(Api); items = signal<Variable[]>([]); error = signal(''); message = signal(''); busy = signal(false);
  name = ''; value = ''; reserved = ['APIKEY_GEMINI', 'APIKEY_OPENAI', 'USAR_GEMINI', 'GEMINI_MODEL', 'OPENAI_MODEL'];
  constructor() { void this.load(); }
  async load() { try { const rows = await this.api.request<Variable[]>('/admin/configuration'); this.items.set(rows.map(v => ({...v, edit: v.secret ? '' : v.value || ''}))); } catch (e) { this.error.set((e as Error).message); } }
  async action(work: () => Promise<unknown>) { this.busy.set(true); this.error.set(''); this.message.set(''); try { await work(); await this.load(); this.message.set('Configuración guardada.'); } catch (e) { this.error.set((e as Error).message); } finally { this.busy.set(false); } }
  save(v: Variable) { void this.action(() => this.api.write('/admin/configuration/' + v.name, 'PUT', {value: v.edit || ''})); }
  create() { this.name = this.name.toUpperCase(); if (this.items().some(v => v.name === this.name)) { this.error.set('La variable ya existe. Usa Guardar en su fila.'); return; } void this.action(async () => { await this.api.write('/admin/configuration/' + encodeURIComponent(this.name), 'PUT', {value: this.value}); this.name = ''; this.value = ''; }); }
  remove(v: Variable) { if (confirm('¿Eliminar ' + v.name + '?')) void this.action(() => this.api.write('/admin/configuration/' + v.name, 'DELETE')); }
}
