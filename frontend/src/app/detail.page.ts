import { Component, inject, signal, OnInit, OnDestroy } from "@angular/core";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { DatePipe, JsonPipe } from "@angular/common";
import { Api, ApiError } from "./api";
import { DocumentRecord, Result, StateEvent, ReviewAudit, label } from "./models";
import { ReviewForm } from "./review.form";
@Component({
  selector: "app-detail",
  imports: [RouterLink, DatePipe, JsonPipe, ReviewForm],
  templateUrl: "./detail.page.html",
})
export class DetailPage implements OnInit, OnDestroy {
  api = inject(Api);
  route = inject(ActivatedRoute);
  id = this.route.snapshot.paramMap.get("id")!;
  doc = signal<DocumentRecord | null>(null);
  result = signal<Result | null>(null);
  history = signal<StateEvent[]>([]);
  reviews = signal<ReviewAudit[]>([]);
  busy = signal(false);
  loading = signal(true);
  error = signal("");
  fileError = signal("");
  original = signal<string | null>(null);
  label = label;
  previewImage = signal<string | null>(null);
  pageNumber = signal(1);
  pageCount = signal(1);
  previewBusy = signal(false);
  previewError = signal("");
  private destroyed = false;
  async ngOnInit() {
    await this.load();
    if (this.doc() && this.doc()!.status !== "RECHAZADO") await this.loadOriginal();
  }
  async load() {
    this.loading.set(true);
    try {
      this.doc.set(await this.api.get(this.id));
      const [result, history, reviews] = await Promise.all([
        this.api.result(this.id).catch((e) => {
          if (e instanceof ApiError && e.status === 409) return null;
          throw e;
        }),
        this.api.history(this.id),
        this.api.reviews(this.id),
      ]);
      this.result.set(result);
      this.history.set(history);
      this.reviews.set(reviews);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }
  async loadOriginal() {
    this.fileError.set("");
    try {
      const blob = await this.api.original(this.id);
      if (this.destroyed) return;
      if (this.original()) URL.revokeObjectURL(this.original()!);
      const url = URL.createObjectURL(blob);
      this.original.set(url);
      if (this.doc()?.format === "pdf") await this.showPage(1);
    } catch (e) {
      this.fileError.set((e as Error).message);
    }
  }
  async showPage(page: number) {
    if (this.previewBusy()) return;
    this.previewBusy.set(true);
    this.previewError.set("");
    try {
      const result = await this.api.preview(this.id, page);
      if (this.destroyed) return;
      if (this.previewImage()) URL.revokeObjectURL(this.previewImage()!);
      this.previewImage.set(URL.createObjectURL(result.blob));
      this.pageCount.set(result.pages);
      this.pageNumber.set(page);
    } catch (e) {
      this.previewError.set((e as Error).message);
    } finally {
      this.previewBusy.set(false);
    }
  }
  canProcess() {
    return this.doc() && ["VALIDADO", "FALLO_TECNICO", "EVALUADO"].includes(this.doc()!.status);
  }
  async process() {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set("");
    try {
      await this.api.process(this.id);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      await this.load();
      this.busy.set(false);
    }
  }
  async reviewed() {
    this.error.set("");
    await this.load();
  }
  ngOnDestroy() {
    this.destroyed = true;
    if (this.previewImage()) URL.revokeObjectURL(this.previewImage()!);
    if (this.original()) URL.revokeObjectURL(this.original()!);
  }
}
