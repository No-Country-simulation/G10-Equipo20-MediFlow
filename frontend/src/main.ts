import { registerLocaleData } from "@angular/common";
import localeEsEc from "@angular/common/locales/es-EC";
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
const roleGuard = (role: string, fallback: string) => async () => {
  const api = inject(Api);
  const router = inject(Router);
  try {
    const account = await api.me();
    return account.role === role ? true : router.parseUrl(fallback);
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
      { path: "", component: App, canActivateChild: [roleGuard("SUPERADMIN", "/administradores")], children: [
        { path: "documents", component: DocumentsPage },
        { path: "documents/:id", component: DetailPage },
        { path: "inboxes", component: InboxesPage },
        { path: "destinations/:code/documents", component: InboxesPage },
        { path: "patients", component: PatientsPage },
        { path: "patients/:id", component: PatientDetailPage },
        { path: "destinations", component: DestinationsPage },
      ] },
      { path: "**", redirectTo: "login" },
    ]),
  ],
}).catch(() => console.error("No se pudo iniciar MediFlow"));
