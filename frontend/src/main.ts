import { registerLocaleData } from "@angular/common";
import localeEsEc from "@angular/common/locales/es-EC";
registerLocaleData(localeEsEc);
import { bootstrapApplication } from "@angular/platform-browser";
import { provideRouter } from "@angular/router";
import { App } from "./app/app";
import { DocumentsPage } from "./app/documents.page";
import { DetailPage } from "./app/detail.page";
import { DestinationsPage } from "./app/destinations.page";
import { InboxesPage } from "./app/inboxes.page";
import { PatientsPage } from "./app/patients.page";
import { PatientDetailPage } from "./app/patient-detail.page";
bootstrapApplication(App, {
  providers: [
    provideRouter([
      { path: "", component: DocumentsPage },
      { path: "documents/:id", component: DetailPage },
      { path: "inboxes", component: InboxesPage },
      { path: "destinations/:code/documents", component: InboxesPage },
      { path: "patients", component: PatientsPage },
      { path: "patients/:id", component: PatientDetailPage },
      { path: "destinations", component: DestinationsPage },
      { path: "**", redirectTo: "" },
    ]),
  ],
}).catch(() => console.error("No se pudo iniciar MediFlow"));
