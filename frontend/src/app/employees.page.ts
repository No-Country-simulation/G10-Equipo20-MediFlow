import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';
import { Permission, Role } from './access.page';
interface Employee {id?: number; name: string; country: string; identity_number: string; contact: string; email: string; password?: string; role_id: number; role_name?: string; active: boolean; denied_permissions: string[];}
const blank = (): Employee => ({name:'',country:'EC',identity_number:'',contact:'',email:'',password:'',role_id:0,active:true,denied_permissions:[]});
@Component({selector:'app-employees',imports:[FormsModule],template:`
  <div class="page-heading"><div><p class="eyebrow">SUPERADMIN · GLOBAL</p><h1>Empleados</h1><p class="subtitle">Acceso mediante email y contraseña en /administradores.</p></div><button class="secondary" (click)="reset()">Nuevo empleado</button></div>
  @if (error()) { <p class="error" role="alert">{{ error() }}</p> } @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
  <section class="panel admin-panel"><div class="table-scroll"><table><thead><tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
  @for (e of items(); track e.id) { <tr><td>{{ e.name }}</td><td>{{ e.email }}</td><td>{{ e.role_name }}</td><td>{{ e.active ? 'Activo' : 'Inactivo' }}</td><td><button class="secondary" (click)="edit(e)">Editar</button></td></tr> }</tbody></table></div>
  @if (!items().length) { <div class="empty">Aún no hay empleados. Crea el primero con el formulario.</div> }
  <form class="admin-form" (ngSubmit)="save()"><h2>{{ form.id ? 'Editar empleado' : 'Crear empleado' }}</h2><div class="form-grid">
  <label>Nombres<input name="name" [(ngModel)]="form.name" required minlength="2" maxlength="255" /></label>
  <label>País de identificación<select name="country" [(ngModel)]="form.country">@for (c of api.countries(); track c.code) { <option [value]="c.code">{{ c.name }}</option> }</select></label>
  <label>Identificación<input name="identity" [(ngModel)]="form.identity_number" required maxlength="40" /></label>
  <label>Contacto<input name="contact" [(ngModel)]="form.contact" maxlength="100" /></label>
  <label>Email<input name="email" type="email" [(ngModel)]="form.email" required /></label>
  <label>{{ form.id ? 'Nueva contraseña (vacío conserva la actual)' : 'Contraseña' }}<input name="password" type="password" [(ngModel)]="form.password" [required]="!form.id" minlength="8" maxlength="128" autocomplete="new-password" /></label>
  <label>Rol<select aria-label="Rol" name="role" [(ngModel)]="form.role_id" required><option [ngValue]="0" disabled>Selecciona un rol</option>@for (r of roles(); track r.id) { <option [ngValue]="r.id">{{ r.name }}</option> }</select></label>
  <label class="check-option"><input name="active" type="checkbox" [(ngModel)]="form.active" /> Cuenta activa</label></div>
  <fieldset class="permission-options"><legend>Negaciones explícitas · prevalecen sobre el rol</legend>@for (p of permissions(); track p.code) { <label class="check-option"><input type="checkbox" [checked]="form.denied_permissions.includes(p.code)" (change)="toggle(p.code)" /> Denegar {{ p.name }}</label> }</fieldset>
  <button class="primary" [disabled]="busy() || !form.role_id">Guardar empleado</button></form></section>`})
export class EmployeesPage {
  api=inject(Api); items=signal<Employee[]>([]); roles=signal<Role[]>([]); permissions=signal<Permission[]>([]); error=signal(''); message=signal(''); busy=signal(false); form=blank();
  constructor() { void this.load(); }
  async load() { try { const [e,r,p] = await Promise.all([this.api.request<Employee[]>('/admin/employees'),this.api.request<Role[]>('/admin/roles'),this.api.request<Permission[]>('/admin/permissions')]); this.items.set(e);this.roles.set(r);this.permissions.set(p); } catch(e) { this.error.set((e as Error).message); } }
  reset() { this.form=blank(); this.message.set(''); }
  edit(e: Employee) { this.form={...e,password:'',denied_permissions:[...e.denied_permissions]}; this.message.set(''); }
  toggle(p: string) { this.form.denied_permissions=this.form.denied_permissions.includes(p) ? this.form.denied_permissions.filter(v=>v!==p) : [...this.form.denied_permissions,p]; }
  async save() { this.busy.set(true);this.error.set('');this.message.set(''); try { const {id,role_name,password,...data}=this.form; await this.api.write('/admin/employees'+(id?'/'+id:''),id?'PUT':'POST',{...data,...(password?{password}:{})});this.reset();await this.load();this.message.set('Empleado guardado.'); } catch(e) {this.error.set((e as Error).message);} finally{this.busy.set(false);} }
}
