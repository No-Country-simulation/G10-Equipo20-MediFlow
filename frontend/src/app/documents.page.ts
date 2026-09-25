import { Component, inject, signal, OnInit } from "@angular/core";
import { Router, RouterLink } from "@angular/router";
import { FormsModule } from "@angular/forms";
import { DatePipe } from "@angular/common";
import { Api } from "./api";
import { DocumentRecord, STATUSES, label } from "./models";
@Component({
  selector: "app-documents",
  imports: [RouterLink, FormsModule, DatePipe],
  templateUrl: "./documents.page.html",
})
export class DocumentsPage implements OnInit {
  api = inject(Api);
  router = inject(Router);
  items = signal<DocumentRecord[]>([]);
  total = signal(0);
  loading = signal(false);
  uploading = signal(false);
  error = signal("");
  uploadError = signal("");
  file = signal<File | null>(null);
  offset = signal(0);
  status = "";
  search = "";
  statuses = STATUSES;
  label = label;
  private sequence = 0;
  async ngOnInit() {
    await Promise.all([this.load(), this.api.configure().catch(() => {})]);
  }
  async load(reset = false) {
    if (reset) this.offset.set(0);
    const seq = ++this.sequence;
    this.loading.set(true);
    this.error.set("");
    try {
      const data = await this.api.list(this.status, this.search, this.offset());
      if (seq === this.sequence) {
        this.items.set(data.items);
        this.total.set(data.total);
      }
    } catch (e) {
      if (seq === this.sequence) this.error.set((e as Error).message);
    } finally {
      if (seq === this.sequence) this.loading.set(false);
    }
  }
  choose(event: Event) {
    this.selectFile((event.target as HTMLInputElement).files?.[0] ?? null);
  }
  drop(event: DragEvent) {
    event.preventDefault();
    if (!this.uploading()) this.selectFile(event.dataTransfer?.files[0] ?? null);
  }
  selectFile(file: File | null) {
    this.uploadError.set("");
    this.file.set(null);
    if (!file) return;
    if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) {
      this.uploadError.set("Selecciona un PDF, JPG o PNG.");
      return;
    }
    if (!file.size || file.size > this.api.config().max_upload_bytes) {
      this.uploadError.set("El archivo debe tener contenido y no superar el límite de tamaño.");
      return;
    }
    this.file.set(file);
  }
  async upload() {
    const file = this.file();
    if (!file || this.uploading()) return;
    this.uploading.set(true);
    this.uploadError.set("");
    try {
      const doc = await this.api.upload(file);
      await this.router.navigate(["/documents", doc.document_id]);
    } catch (e) {
      this.uploadError.set((e as Error).message);
      await this.load();
    } finally {
      this.uploading.set(false);
    }
  }
  page(direction: number) {
    this.offset.update((n) => Math.max(0, n + direction * 20));
    void this.load();
  }
  size(bytes: number | null) {
    return bytes === null
      ? "—"
      : bytes < 1024
        ? bytes + " B"
        : bytes < 1048576
          ? (bytes / 1024).toFixed(0) + " KB"
          : (bytes / 1048576).toFixed(1) + " MB";
  }
}
