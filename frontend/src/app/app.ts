import { Component, inject, OnInit, signal } from "@angular/core";
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { Api } from "./api";
@Component({
  selector: "app-admin-shell", imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `<div class="shell" [class.menu-open]="menuOpen()">
    @if (menuOpen()) { <button class="menu-overlay" aria-label="Cerrar menú" (click)="menuOpen.set(false)"></button> }
    <aside class="sidebar"><a routerLink="/home" class="brand" (click)="menuOpen.set(false)">MediFlow</a><p class="brand-caption">Gestión y triaje documental</p>
      <div class="workspace-label">OPERACIÓN</div><nav aria-label="Navegación principal" (click)="menuOpen.set(false)">
      @if (api.can('DOCUMENTS_READ')) {
        <a routerLink="/home" routerLinkActive="active" class="nav-item">⌂ <span>Inicio</span></a>
        <a routerLink="/documents" routerLinkActive="active" class="nav-item">▤ <span>Documentos</span></a>
        <a routerLink="/review" routerLinkActive="active" class="nav-item">✓ <span>Revisión humana</span></a>
        <a routerLink="/inboxes" routerLinkActive="active" class="nav-item">▧ <span>Bandejas</span></a>
      }
      @if (api.can('PATIENTS_READ')) { <a routerLink="/patients" routerLinkActive="active" class="nav-item">♙ <span>Pacientes</span></a> }
      @if (api.can('DESTINATIONS_MANAGE')) { <div class="workspace-label">CONFIGURACIÓN GLOBAL</div><a routerLink="/destinations" routerLinkActive="active" [routerLinkActiveOptions]="{exact:true}" class="nav-item">◇ <span>Destinos y reglas</span></a> }
      @if (api.account()?.role === 'SUPERADMIN') { <div class="workspace-label">SUPERADMIN</div>
        <a routerLink="/configuration" routerLinkActive="active" class="nav-item">⚙ <span>Variables de Configuración</span></a>
        <a routerLink="/roles-permissions" routerLinkActive="active" class="nav-item">◇ <span>Roles y Permisos</span></a>
        <a routerLink="/employees" routerLinkActive="active" class="nav-item">♙ <span>Empleados</span></a>
      }</nav>
      <div class="account"><span class="avatar">{{ api.account()?.role === 'SUPERADMIN' ? 'SA' : 'EM' }}</span><div>{{ api.account()?.name || (api.account()?.role === 'SUPERADMIN' ? 'Superadministrador' : 'Empleado') }}<small>Sesión local</small></div></div>
      <button class="signout" (click)="logout()">Cerrar sesión</button>
    </aside><div class="workspace"><header class="topbar">
      <button class="menu-toggle secondary" aria-label="Abrir menú" [attr.aria-expanded]="menuOpen()" (click)="menuOpen.update(toggle)">☰</button>
      <span>MediFlow <span class="slash">/</span> Gestión documental</span>
      <label class="locale">País<select aria-label="País de trabajo" [value]="api.country()" (change)="changeCountry($event)">
        @for (country of api.countries(); track country.code) { <option [value]="country.code" [selected]="country.code === api.country()">{{ country.name }}</option> }
      </select></label></header><main><router-outlet /></main><footer>Prioridad y alertas locales basadas en texto explícito.</footer></div></div>`
})
export class App implements OnInit {
  api=inject(Api); router=inject(Router); menuOpen=signal(false); toggle=(value:boolean)=>!value;
  ngOnInit() { void this.api.configure().catch(()=>{}); }
  changeCountry(event:Event) { this.api.selectCountry((event.target as HTMLSelectElement).value); }
  async logout() { await this.api.logout(); this.api.account.set(null); await this.router.navigateByUrl('/administradores'); }
}
