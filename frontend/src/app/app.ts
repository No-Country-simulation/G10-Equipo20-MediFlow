import { Component, inject, OnInit } from "@angular/core";
import { RouterLink, RouterOutlet } from "@angular/router";
import { Api } from "./api";
@Component({
  selector: "app-root",
  imports: [RouterLink, RouterOutlet],
  template: ` <div class="shell">
    <aside class="sidebar">
      <a routerLink="/" class="brand">MediFlow</a>
      <div class="workspace-label">ESPACIO DE TRABAJO</div>
      <a routerLink="/" class="nav-item">▤ <span>Documentos</span></a>
      <a routerLink="/inboxes" class="nav-item">▧ <span>Bandejas</span></a>
      <a routerLink="/patients" class="nav-item">♙ <span>Pacientes</span></a>
      <a routerLink="/destinations" class="nav-item">◇ <span>Destinos</span></a>
      <div class="account">
        <span class="avatar">SA</span>
        <div>Superadministrador<small>Acceso local · sin sesión</small></div>
      </div>
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
        Entorno local sin autenticación · Prioridad y alertas locales basadas en texto explícito.
      </footer>
    </div>
  </div>`,
})
export class App implements OnInit {
  api = inject(Api);
  ngOnInit() { void this.api.configure().catch(() => {}); }
  changeCountry(event: Event) {
    this.api.selectCountry((event.target as HTMLSelectElement).value);
  }
}
