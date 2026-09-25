import { registerLocaleData } from "@angular/common";
import localeEsEc from "@angular/common/locales/es-EC";
registerLocaleData(localeEsEc);
import { bootstrapApplication } from "@angular/platform-browser";
import { provideRouter } from "@angular/router";
import { App } from "./app/app";
import { DocumentsPage } from "./app/documents.page";
import { DetailPage } from "./app/detail.page";
bootstrapApplication(App, {
  providers: [
    provideRouter([
      { path: "", component: DocumentsPage },
      { path: "documents/:id", component: DetailPage },
      { path: "**", redirectTo: "" },
    ]),
  ],
}).catch(() => console.error("No se pudo iniciar MediFlow"));
