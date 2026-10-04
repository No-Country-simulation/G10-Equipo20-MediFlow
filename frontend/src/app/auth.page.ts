import { Component, inject, OnInit, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { Router, RouterLink } from "@angular/router";
import { Api } from "./api";

@Component({
  selector: "app-auth",
  imports: [FormsModule, RouterLink],
  template: `
  <div class="auth-layout">
    <section class="auth-intro">
      <div class="auth-mark">MediFlow</div>
      <h1>Tu información de salud, en un solo lugar.</h1>
      <p>Consulta los documentos asociados a tu identificación de forma sencilla.</p>
      <div class="auth-features"><span>▤ Resultados</span><span>▣ Informes</span><span>⊞ Órdenes</span></div>
    </section>
    <section class="auth-card">
      <div class="auth-logo">◈ <strong>MediFlow</strong></div>
      @if (!admin()) {
        <div class="auth-tabs"><a routerLink="/login" [class.selected]="!register()">Iniciar sesión</a><a routerLink="/registro" [class.selected]="register()">Crear cuenta</a></div>
      } @else { <h2>Acceso administrativo</h2> }
      <form (ngSubmit)="submit()">
        @if (!admin()) {
          <label>País
            <select name="country" [(ngModel)]="country" required>
              @for (item of api.countries(); track item.code) { <option [value]="item.code">{{ item.name }}</option> }
            </select>
          </label>
          <label>Documento de identidad<input name="identity" [(ngModel)]="identity" autocomplete="username" required placeholder="Cédula o identificación" /></label>
        }
        @if (register() || admin()) {
          <label>Correo electrónico<input name="email" type="email" [(ngModel)]="email" autocomplete="email" required placeholder="correo@ejemplo.com" /></label>
        }
        <label>Contraseña<input name="password" type="password" [(ngModel)]="password" autocomplete="current-password" required minlength="8" placeholder="Contraseña" /></label>
        @if (register()) {
          <label>Confirmar contraseña<input name="confirmation" type="password" [(ngModel)]="confirmation" autocomplete="new-password" required placeholder="Confirma tu contraseña" /></label>
          <p class="auth-policy">Al continuar aceptas las <a href="#" (click)="$event.preventDefault()">políticas de uso</a> y el <a href="#" (click)="$event.preventDefault()">tratamiento de datos personales</a>. Estos textos estarán disponibles más adelante.</p>
        }
        @if (error()) { <p class="auth-error" role="alert">{{ error() }}</p> }
        @if (message()) { <p class="auth-success" role="status">{{ message() }}</p> }
        <button type="submit" class="auth-submit" [disabled]="busy()">{{ busy() ? 'Espera…' : admin() ? 'Ingresar' : register() ? 'Registrar' : 'Ingresar' }}</button>
      </form>
    </section>
  </div>`,
})
export class AuthPage implements OnInit {
  api = inject(Api);
  router = inject(Router);
  country = this.api.country();
  identity = "";
  email = "";
  password = "";
  confirmation = "";
  busy = signal(false);
  error = signal("");
  message = signal("");
  admin = () => this.router.url.startsWith("/administradores");
  register = () => this.router.url.startsWith("/registro");
  ngOnInit() { void this.api.configure().then(() => this.country = this.api.country()).catch(() => {}); }
  async submit() {
    if (this.busy()) return;
    this.error.set(""); this.message.set("");
    if (this.register() && this.password !== this.confirmation) { this.error.set("Las contraseñas no coinciden."); return; }
    this.busy.set(true);
    try {
      if (this.admin()) {
        await this.api.adminLogin({email: this.email, password: this.password});
        await this.api.me();
        await this.router.navigateByUrl(this.api.can("DOCUMENTS_READ") ? "/home" : this.api.can("PATIENTS_READ") ? "/patients" : this.api.can("DESTINATIONS_MANAGE") ? "/destinations" : "/sin-acceso");
      } else if (this.register()) {
        await this.api.register({country: this.country, identity_number: this.identity, email: this.email, password: this.password});
        this.message.set("Cuenta creada. Ya puedes iniciar sesión.");
        this.password = ""; this.confirmation = "";
      } else {
        await this.api.patientLogin({country: this.country, identity_number: this.identity, password: this.password});
        this.api.selectCountry(this.country);
        await this.router.navigateByUrl("/portal");
      }
    } catch (e) { this.error.set((e as Error).message); }
    finally { this.busy.set(false); }
  }
}
