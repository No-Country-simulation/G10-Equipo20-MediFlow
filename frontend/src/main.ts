import { registerLocaleData } from "@angular/common";
import localeEsEc from "@angular/common/locales/es-EC";
import { PoliciesPage } from "./app/policies.page";
registerLocaleData(localeEsEc);
import { bootstrapApplication } from "@angular/platform-browser";
import { provideRouter } from "@angular/router";
import { App } from "./app/app";
import { Root } from "./app/root";
import { AuthPage } from "./app/auth.page";
import { PortalPage } from "./app/portal.page";
import { inject } from "@angular/core";
import { Router } from "@angular/router";
import { Api } from "./app/api";
import { DocumentsPage } from "./app/documents.page";
import { DetailPage } from "./app/detail.page";
import { DestinationsPage } from "./app/destinations.page";
import { InboxesPage } from "./app/inboxes.page";
import { PatientsPage } from "./app/patients.page";
import { PatientDetailPage } from "./app/patient-detail.page";
import { HomePage } from "./app/home.page";
import { ReviewPage } from "./app/review.page";
import { Component } from "@angular/core";
import { SettingsPage } from "./app/settings.page";
import { AccessPage } from "./app/access.page";
import { EmployeesPage } from "./app/employees.page";
@Component({selector: 'app-no-access', template: '<div class="empty"><h1>Sin permisos de acceso</h1><p>Solicita al superadministrador que revise tu rol y las negaciones de tu cuenta.</p></div>'})
class NoAccessPage {}
const permissionGuard = (code: string) => async () => {
  const api = inject(Api); const router = inject(Router);
  try { await api.me(); return api.can(code) ? true : router.parseUrl('/sin-acceso'); }
  catch { return router.parseUrl('/administradores'); }
};
const roleGuard = (role: string, fallback: string) => async () => {
  const api = inject(Api);
  const router = inject(Router);
  try {
    const account = await api.me();
    return (account.role === role || (role === "STAFF" && account.role === "EMPLOYEE") || (role === "STAFF" && account.role === "SUPERADMIN")) ? true : router.parseUrl(fallback);
  } catch { return router.parseUrl(fallback); }
};
bootstrapApplication(Root, {
  providers: [
    provideRouter([
      { path: "", pathMatch: "full", redirectTo: "login" },
      { path: "login", component: AuthPage },
      { path: "registro", component: AuthPage },
      { path: "administradores", component: AuthPage },
      { path: "portal", component: PortalPage, canActivate: [roleGuard("PATIENT", "/login")] },
      { path: "", component: App, canActivateChild: [roleGuard("STAFF", "/administradores")], children: [
        { path: "sin-acceso", component: NoAccessPage },
        { path: "configuration", component: SettingsPage, canActivate: [roleGuard("SUPERADMIN", "/sin-acceso")] },
        { path: "document-policies", component: PoliciesPage, canActivate: [roleGuard("SUPERADMIN", "/sin-acceso")] },
        { path: "roles-permissions", component: AccessPage, canActivate: [roleGuard("SUPERADMIN", "/sin-acceso")] },
        { path: "employees", component: EmployeesPage, canActivate: [roleGuard("SUPERADMIN", "/sin-acceso")] },
        { path: "home", canActivate: [permissionGuard("DOCUMENTS_READ")], component: HomePage },
        { path: "review", canActivate: [permissionGuard("DOCUMENTS_READ")], component: ReviewPage },
        { path: "review/:id", canActivate: [permissionGuard("DOCUMENTS_READ")], component: DetailPage },
        { path: "documents", canActivate: [permissionGuard("DOCUMENTS_READ")], component: DocumentsPage },
        { path: "documents/:id", canActivate: [permissionGuard("DOCUMENTS_READ")], component: DetailPage },
        { path: "inboxes", canActivate: [permissionGuard("DOCUMENTS_READ")], component: InboxesPage },
        { path: "destinations/:code/documents", canActivate: [permissionGuard("DOCUMENTS_READ")], component: InboxesPage },
        { path: "patients", canActivate: [permissionGuard("PATIENTS_READ")], component: PatientsPage },
        { path: "patients/:id", canActivate: [permissionGuard("PATIENTS_READ")], component: PatientDetailPage },
        { path: "destinations", canActivate: [permissionGuard("DESTINATIONS_MANAGE")], component: DestinationsPage },
      ] },
      { path: "**", redirectTo: "login" },
    ]),
  ],
}).catch(() => console.error("No se pudo iniciar MediFlow"));
