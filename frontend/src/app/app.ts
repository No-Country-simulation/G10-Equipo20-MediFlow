import { Component } from "@angular/core";
import { RouterLink, RouterOutlet } from "@angular/router";
@Component({
  selector: "app-root",
  imports: [RouterLink, RouterOutlet],
  template: ` <div class="shell">
    <aside class="sidebar">
      <a routerLink="/" class="brand"
        ><span class="brand-icon">m<span>+</span></span
        >MediFlow</a
      >
      <div class="workspace-label">ESPACIO DE TRABAJO</div>
      <a routerLink="/" class="nav-item">▤ <span>Documentos</span></a>
      <div class="sidebar-note">
        <span class="pulse"></span> Centro cardiopulmonar
        <p>Triaje documental</p>
      </div>
      <div class="account">
        <span class="avatar">SA</span>
        <div>Superadministrador<small>Acceso local · sin sesión</small></div>
      </div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <span>MediFlow <span class="slash">/</span> Gestión documental</span
        ><span class="locale">EC <span>Ecuador</span></span>
      </header>
      <main><router-outlet /></main>
      <footer>
        Entorno local sin autenticación · Prioridad clínica y alertas pendientes de implementación.
      </footer>
    </div>
  </div>`,
})
export class App {}
