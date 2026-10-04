import { Component, inject, signal, OnInit, OnDestroy } from "@angular/core";
import { ActivatedRoute, Router, RouterLink } from "@angular/router";
import { DatePipe, JsonPipe } from "@angular/common";
import { Api, ApiError } from "./api";
import { DocumentRecord, Result, StateEvent, ReviewAudit, label } from "./models";
import { ReviewForm } from "./review.form";
import { Subscription } from "rxjs";
@Component({
  selector: "app-detail",
  imports: [RouterLink, DatePipe, JsonPipe, ReviewForm],
  templateUrl: "./detail.page.html",
})
export class DetailPage implements OnInit, OnDestroy {
  api = inject(Api);
  route = inject(ActivatedRoute);
  router = inject(Router);
  id = this.route.snapshot.paramMap.get("id")!;
  reviewMode = this.route.snapshot.routeConfig?.path === 'review/:id';
  reviewOffset = Math.max(0, Number(this.route.snapshot.queryParamMap.get('offset')) || 0);
  previousCase = signal<string | null>(null);
  nextCase = signal<string | null>(null);
  mobilePanel = signal('result');
  private routeSubscription?: Subscription;
  private sequence = 0;
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
    this.routeSubscription = this.route.paramMap.subscribe(params => {
      this.id = params.get('id')!;
      this.sequence++;
      this.doc.set(null); this.result.set(null); this.history.set([]); this.reviews.set([]); this.error.set('');
      this.fileError.set(''); this.previewError.set(''); this.pageNumber.set(1); this.pageCount.set(1);
      if (this.original()) URL.revokeObjectURL(this.original()!);
      if (this.previewImage()) URL.revokeObjectURL(this.previewImage()!);
      this.original.set(null); this.previewImage.set(null); this.previewBusy.set(false);
      void this.openCase();
    });
    if (this.reviewMode) {
      try {
        const data = await this.api.list('EN_REVISION_HUMANA', '', this.reviewOffset);
        this.caseIds = data.items.map(doc => doc.document_id);
        this.updateNeighbors();
      } catch (e) { this.error.set((e as Error).message); }
    }
  }
  private caseIds: string[] = [];
  private updateNeighbors() {
    const index = this.caseIds.indexOf(this.id);
    this.previousCase.set(index > 0 ? this.caseIds[index - 1] : null);
    this.nextCase.set(index >= 0 ? this.caseIds[index + 1] || null : null);
  }
  private async openCase() {
    const seq = this.sequence;
    this.updateNeighbors(); await this.load();
    if (seq === this.sequence && this.doc() && (this.doc()!.status !== 'RECHAZADO' || !!this.result())) await this.loadOriginal();
  }
  async load() {
    const seq = this.sequence, id = this.id;
    this.loading.set(true);
    try {
      const doc = await this.api.get(id);
      const [result, history, reviews] = await Promise.all([
        this.api.result(id).catch((e) => {
          if (e instanceof ApiError && e.status === 409) return null;
          throw e;
        }),
        this.api.history(id),
        this.api.reviews(id),
      ]);
      if (seq !== this.sequence || this.destroyed) return;
      this.doc.set(doc); this.result.set(result);
      this.history.set(history);
      this.reviews.set(reviews);
    } catch (e) {
      if (seq === this.sequence) this.error.set((e as Error).message);
    } finally {
      if (seq === this.sequence) this.loading.set(false);
    }
  }
  async loadOriginal() {
    const seq = this.sequence;
    this.fileError.set("");
    try {
      const blob = await this.api.original(this.id);
      if (this.destroyed || seq !== this.sequence) return;
      if (this.original()) URL.revokeObjectURL(this.original()!);
      const url = URL.createObjectURL(blob);
      this.original.set(url);
      if (this.doc()?.format === "pdf") await this.showPage(1);
    } catch (e) {
      if (seq === this.sequence) this.fileError.set((e as Error).message);
    }
  }
  async showPage(page: number) {
    const seq = this.sequence;
    if (this.previewBusy()) return;
    this.previewBusy.set(true);
    this.previewError.set("");
    try {
      const result = await this.api.preview(this.id, page);
      if (this.destroyed || seq !== this.sequence) return;
      if (this.previewImage()) URL.revokeObjectURL(this.previewImage()!);
      this.previewImage.set(URL.createObjectURL(result.blob));
      this.pageCount.set(result.pages);
      this.pageNumber.set(page);
    } catch (e) {
      if (seq === this.sequence) this.previewError.set((e as Error).message);
    } finally {
      if (seq === this.sequence) this.previewBusy.set(false);
    }
  }
  canProcess() {
    return this.api.can("DOCUMENTS_PROCESS") && this.doc() && ["VALIDADO", "FALLO_TECNICO", "EVALUADO"].includes(this.doc()!.status);
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
  async deleteDocument() {
    const doc = this.doc();
    if (!doc || this.busy() || !confirm(`¿Eliminar definitivamente «${doc.original_filename}» y todos sus datos?`)) return;
    this.busy.set(true);
    this.error.set("");
    try {
      await this.api.deleteDocument(doc.document_id);
      await this.router.navigate(["/documents"]);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }
  ngOnDestroy() {
    this.destroyed = true;
    this.routeSubscription?.unsubscribe();
    if (this.previewImage()) URL.revokeObjectURL(this.previewImage()!);
    if (this.original()) URL.revokeObjectURL(this.original()!);
  }
}
