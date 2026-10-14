import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';

interface SMTPConfig {
  enabled: boolean; host: string; port: number; security: 'STARTTLS' | 'SSL_TLS';
  username: string; sender: string; password_configured: boolean;
}

@Component({selector: 'app-smtp-settings', imports: [FormsModule], template: `
  <section class="panel admin-panel">
    <h2>Configuración SMTP</h2>
    <p class="muted">Base para avisos por email al entregarse un documento o ingresar a revisión humana.
      El envío está desactivado por defecto. Los destinatarios se definen al editar cada destino.</p>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (message()) { <p class="notice" role="status">{{ message() }}</p> }
    @if (loaded()) {
      <form class="admin-form" (ngSubmit)="save()" #form="ngForm">
        <label>Servidor SMTP<input name="smtpHost" [(ngModel)]="config.host" maxlength="255" placeholder="smtp.proveedor.com" /></label>
        <label>Puerto<input name="smtpPort" [(ngModel)]="config.port" type="number" min="1" max="65535" required /></label>
        <label>Seguridad<select name="smtpSecurity" [(ngModel)]="config.security">
          <option value="STARTTLS">STARTTLS (habitualmente 587)</option><option value="SSL_TLS">SSL/TLS (habitualmente 465)</option>
        </select></label>
        <label>Usuario<input name="smtpUsername" [(ngModel)]="config.username" maxlength="255" autocomplete="off" /></label>
        <label>Contraseña<input name="smtpPassword" [(ngModel)]="password" type="password" autocomplete="new-password"
          [placeholder]="config.password_configured ? 'Guardada · deja vacío para conservarla' : 'Sin configurar'" /></label>
        <label class="check-option"><input name="smtpClear" [(ngModel)]="clearPassword" type="checkbox" /> Borrar contraseña guardada</label>
        <label>Email remitente<input name="smtpSender" [(ngModel)]="config.sender" type="email" email placeholder="notificaciones@hospital.com" /></label>
        <label class="check-option"><input name="smtpEnabled" [(ngModel)]="config.enabled" type="checkbox" /> Activar envío por email</label>
        <p class="muted">{{ config.enabled ? 'Al guardar, se habilitarán los avisos de los próximos documentos.' : 'Desactivado: puedes guardar las credenciales sin enviar correos.' }}
          Los avisos contienen un enlace a MediFlow, sin adjuntar documentos clínicos.</p>
        <button class="primary" [disabled]="busy() || form.invalid">{{ busy() ? 'Guardando…' : 'Guardar SMTP' }}</button>
      </form>
    }
  </section>
`})
export class SMTPSettings {
  api = inject(Api); loaded = signal(false); busy = signal(false); error = signal(''); message = signal('');
  password = ''; clearPassword = false;
  config: SMTPConfig = {enabled: false, host: '', port: 587, security: 'STARTTLS', username: '', sender: '', password_configured: false};
  constructor() { void this.load(); }
  async load() {
    try { this.config = await this.api.request<SMTPConfig>('/admin/smtp'); this.loaded.set(true); }
    catch (e) { this.error.set((e as Error).message); }
  }
  async save() {
    if (this.busy()) return;
    this.busy.set(true); this.error.set(''); this.message.set('');
    try {
      const {password_configured, ...fields} = this.config;
      this.config = await this.api.write<SMTPConfig>('/admin/smtp', 'PUT', {...fields,
        ...(this.password ? {password: this.password} : {}), clear_password: this.clearPassword});
      this.password = ''; this.clearPassword = false;
      this.message.set(this.config.enabled ? 'SMTP guardado y envío activado.' : 'SMTP guardado. El envío sigue desactivado.');
    } catch (e) { this.error.set((e as Error).message); }
    finally { this.busy.set(false); }
  }
}
