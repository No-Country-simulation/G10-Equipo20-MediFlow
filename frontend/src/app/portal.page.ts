import { Component, inject, OnInit, signal } from "@angular/core";
import { DatePipe } from "@angular/common";
import { Router } from "@angular/router";
import { Api } from "./api";
import { DocumentRecord, label } from "./models";

@Component({
  selector: "app-patient-portal",
  imports: [DatePipe],
  template: `<div class="portal-shell">
    <header><strong>MediFlow</strong><button (click)="logout()">Cerrar sesión</button></header>
    <main><h1>Mis documentos</h1><p>Documentos vinculados a tu identificación y país de registro.</p>
      @if (error()) { <p role="alert" class="auth-error">{{ error() }}</p> }
      @else if (loading()) { <p>Cargando documentos…</p> }
      @else if (!items().length) { <div class="portal-empty"><h2>Aún no hay documentos asociados</h2><p>Cuando MediFlow identifique documentos con tu número de identificación en el país de tu cuenta, aparecerán aquí.</p></div> }
      @else { <div class="portal-list">@for (item of items(); track item.document_id) {
        <article><div><strong>{{ item.original_filename }}</strong><small>{{ item.received_at | date:'mediumDate' }} · {{ label(item.status) }}</small></div>
        <a [href]="'/api/auth/my-documents/' + item.document_id + '/file'" target="_blank" rel="noopener">Abrir documento</a></article>
      }</div> }
    </main>
  </div>`,
})
export class PortalPage implements OnInit {
  api = inject(Api); router = inject(Router); label = label;
  items = signal<DocumentRecord[]>([]); loading = signal(true); error = signal("");
  async ngOnInit() {
    try { this.items.set(await this.api.myDocuments()); }
    catch (e) { this.error.set((e as Error).message); }
    finally { this.loading.set(false); }
  }
  async logout() { await this.api.logout(); await this.router.navigateByUrl("/login"); }
}
