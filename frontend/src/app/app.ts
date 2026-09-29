import { Component, inject, OnInit } from "@angular/core";
import { Router, RouterLink, RouterOutlet } from "@angular/router";
import { Api } from "./api";
@Component({
  selector: "app-admin-shell",
  imports: [RouterLink, RouterOutlet],
  template: ` <div class="shell">
    <aside class="sidebar">
      <a routerLink="/documents" class="brand">MediFlow</a>
      <div class="workspace-label">ESPACIO DE TRABAJO</div>
      <a routerLink="/documents" class="nav-item">▤ <span>Documentos</span></a>
      <a routerLink="/inboxes" class="nav-item">▧ <span>Bandejas</span></a>
      <a routerLink="/patients" class="nav-item">♙ <span>Pacientes</span></a>
      <a routerLink="/destinations" class="nav-item">◇ <span>Destinos</span></a>
      <div class="account">
        <span class="avatar">SA</span>
        <div>Superadministrador<small>Sesión local</small></div>
      </div>
      <button class="signout" (click)="logout()">Cerrar sesión</button>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <span>MediFlow <span class="slash">/</span> Gestión documental</span
        ><label class="locale">País
          <select aria-label="País de trabajo" [value]="api.country()" (change)="changeCountry($event)">
            @for (country of api.countries(); track country.code) {
              <option [value]="country.code" [selected]="country.code === api.country()">{{ country.name }}</option>
            }
          </select>
        </label>
      </header>
      <main><router-outlet /></main>
      <footer>
        Prioridad y alertas locales basadas en texto explícito.
      </footer>
    </div>
  </div>`,
})
export class App implements OnInit {
  api = inject(Api);
  router = inject(Router);
  ngOnInit() { void this.api.configure().catch(() => {}); }
  changeCountry(event: Event) {
    this.api.selectCountry((event.target as HTMLSelectElement).value);
  }
  async logout() { await this.api.logout(); await this.router.navigateByUrl("/administradores"); }
}
