import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';
export interface Permission {code: string; name: string; builtin: boolean;}
export interface Role {id: number; name: string; permissions: string[];}
@Component({selector: 'app-access', imports: [FormsModule], template: `
  <div class="page-heading"><div><p class="eyebrow">SUPERADMIN</p><h1>Roles y Permisos</h1><p class="subtitle">El rol concede permisos. Una negación en el empleado siempre prevalece.</p></div></div>
  @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
  <div class="admin-grid"><section class="panel admin-panel"><h2>Roles</h2>
  <div class="table-scroll"><table><thead><tr><th>Rol</th><th>Permisos</th><th>Acciones</th></tr></thead><tbody>
  @for (r of roles(); track r.id) { <tr><td>{{ r.name }}</td><td>{{ r.permissions.length }}</td><td class="row-actions"><button class="secondary" (click)="edit(r)">Editar</button><button class="danger" (click)="removeRole(r)" [disabled]="busy()">Eliminar</button></td></tr> }</tbody></table></div>
  <form class="admin-form" (ngSubmit)="saveRole()"><h3>{{ roleId ? 'Editar rol' : 'Crear rol' }}</h3><label>Nombre<input name="roleName" [(ngModel)]="roleName" required minlength="2" maxlength="100" /></label>
  <fieldset class="permission-options"><legend>Permisos concedidos</legend>@for (p of permissions(); track p.code) { <label class="check-option"><input type="checkbox" [checked]="grants.includes(p.code)" (change)="toggle(p.code)" />{{ p.name }}<small>{{ p.code }}</small></label> }</fieldset>
  <div class="row-actions"><button class="primary" [disabled]="busy()">Guardar rol</button><button type="button" class="secondary" (click)="reset()">Nuevo</button></div></form></section>
  <section class="panel admin-panel"><h2>Permisos</h2><p class="muted">Los permisos base están conectados a la API. Un permiso personalizado necesita asociarse a una funcionalidad en código para habilitar acciones.</p>
  <form class="admin-form" (ngSubmit)="savePermission()"><label>Clave<input name="code" [(ngModel)]="code" required pattern="[A-Z][A-Z0-9_]{2,99}" placeholder="CLAVE_EN_MAYUSCULAS" /></label><label>Nombre<input name="permissionName" [(ngModel)]="permissionName" required minlength="2" maxlength="150" /></label><button class="primary" [disabled]="busy()">Crear permiso</button></form>
  <ul class="permission-list">@for (p of permissions(); track p.code) { <li><div>{{ p.name }}<small class="mono">{{ p.code }}</small></div>@if (!p.builtin) { <button class="danger" (click)="removePermission(p)" [disabled]="busy()">Eliminar</button> }</li> }</ul></section></div>`})
export class AccessPage {
  api = inject(Api); permissions = signal<Permission[]>([]); roles = signal<Role[]>([]); error = signal(''); busy = signal(false);
  roleId = 0; roleName = ''; grants: string[] = []; code = ''; permissionName = '';
  constructor() { void this.load(); }
  async load() { try { const [p,r] = await Promise.all([this.api.request<Permission[]>('/admin/permissions'),this.api.request<Role[]>('/admin/roles')]); this.permissions.set(p); this.roles.set(r); } catch (e) { this.error.set((e as Error).message); } }
  async action(work: () => Promise<unknown>) { this.error.set(''); this.busy.set(true); try { await work(); await this.load(); } catch (e) { this.error.set((e as Error).message); } finally { this.busy.set(false); } }
  edit(r: Role) { this.roleId = r.id; this.roleName = r.name; this.grants = [...r.permissions]; }
  reset() { this.roleId = 0; this.roleName = ''; this.grants = []; }
  toggle(code: string) { this.grants = this.grants.includes(code) ? this.grants.filter(p => p !== code) : [...this.grants,code]; }
  saveRole() { void this.action(async () => { await this.api.write('/admin/roles' + (this.roleId ? '/' + this.roleId : ''), this.roleId ? 'PUT' : 'POST', {name: this.roleName, permissions: this.grants}); this.reset(); }); }
  removeRole(r: Role) { if (confirm('¿Eliminar el rol ' + r.name + '?')) void this.action(() => this.api.write('/admin/roles/' + r.id,'DELETE')); }
  savePermission() { void this.action(async () => { await this.api.write('/admin/permissions','POST',{code:this.code.toUpperCase(),name:this.permissionName}); this.code = ''; this.permissionName = ''; }); }
  removePermission(p: Permission) { if (confirm('¿Eliminar ' + p.code + '?')) void this.action(() => this.api.write('/admin/permissions/' + p.code,'DELETE')); }
}
