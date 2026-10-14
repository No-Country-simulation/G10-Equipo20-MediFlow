import { Component, inject, OnInit, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { Api } from "./api";
import { DestinationDetail } from "./models";

@Component({
  selector: "app-destination-edit",
  imports: [FormsModule, RouterLink],
  template: `
    <div class="page-heading"><div><a routerLink="/destinations">← Destinos y reglas</a>
      <h1>EDITAR DESTINO</h1><p class="subtitle">Datos del destino y contactos para notificaciones.</p></div></div>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
    @if (destination(); as item) {
      <form class="panel destination-editor" #form="ngForm" (ngSubmit)="save()">
        <h2>{{ item.name }}</h2>
        <label>Código<input [value]="item.code" readonly aria-label="Código del destino" /></label>
        <label>Nombre<input name="name" [(ngModel)]="item.name" required minlength="2" maxlength="120" /></label>
        <label>Tipo<select name="kind" [(ngModel)]="item.kind">
          <option value="DEPARTMENT">Departamento</option><option value="QUEUE">Cola</option><option value="SYSTEM">Sistema</option>
        </select></label>
        <label>Estado<select name="active" [(ngModel)]="item.active" [disabled]="item.code === 'COLA_URGENCIAS_MEDICAS'">
          <option [ngValue]="true">Activo</option><option [ngValue]="false">Inactivo</option>
        </select></label>
        <label>Slack<input type="password" name="slack" [(ngModel)]="item.slack_webhook_url" maxlength="512"
          autocomplete="new-password" placeholder="https://hooks.slack.com/services/…" aria-describedby="slack-help" /></label>
        <p id="slack-help" class="muted">Webhook del canal que recibirá una notificación cuando un documento llegue a esta bandeja, por entrega o para revisión humana. Deja el campo vacío para desactivar las notificaciones.</p>
        <div class="actions"><button class="primary" [disabled]="busy() || form.invalid">{{ busy() ? 'Guardando…' : 'Guardar cambios' }}</button>
          <a class="secondary" routerLink="/destinations">Volver</a></div>
      </form>
    } @else if (!error()) { <p role="status">Cargando destino…</p> }
  `,
  styles: [`:host {display:block} .destination-editor {max-width:760px;display:grid;gap:16px;padding:24px}
    label {display:grid;gap:8px;font-weight:600} input,select {width:100%;box-sizing:border-box}
    .muted {margin:0;font-weight:400} .actions {display:flex;gap:12px;flex-wrap:wrap}`],
})
export class DestinationEditPage implements OnInit {
  api = inject(Api);
  route = inject(ActivatedRoute);
  destination = signal<DestinationDetail | null>(null);
  error = signal("");
  message = signal("");
  busy = signal(false);
  async ngOnInit() {
    try {
      const item = await this.api.destination(this.route.snapshot.paramMap.get("code") || "");
      this.destination.set(item);
    } catch (error) { this.error.set((error as Error).message); }
  }
  async save() {
    const item = this.destination();
    if (!item || this.busy()) return;
    const slack = item.slack_webhook_url.trim();
    if (slack && !/^https:\/\/hooks\.slack\.com(?::443)?\/services\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(slack)) {
      this.error.set("Introduce un webhook válido de Slack (https://hooks.slack.com/services/…)."); return;
    }
    this.busy.set(true); this.error.set(""); this.message.set("");
    try {
      await this.api.updateDestination(item.code, {name: item.name.trim(), kind: item.kind,
        active: item.active, slack_webhook_url: slack});
      this.message.set("Destino y contactos guardados.");
    } catch (error) { this.error.set((error as Error).message); }
    finally { this.busy.set(false); }
  }
}
