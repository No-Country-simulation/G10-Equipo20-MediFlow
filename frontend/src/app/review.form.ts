import { Component, EventEmitter, Input, Output, OnInit, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { Api } from "./api";
import { Classification, ExtractedField, Page, Result, TYPES, SPECIALTIES, label } from "./models";
@Component({
  selector: "app-review-form",
  imports: [FormsModule],
  templateUrl: "./review.form.html",
})
export class ReviewForm implements OnInit {
  @Input({ required: true }) documentId!: string;
  @Input({ required: true }) result!: Result;
  @Output() completed = new EventEmitter<void>();
  api = inject(Api);
  busy = signal(false);
  error = signal("");
  action = "APPROVE";
  notes = "";
  confirmed = false;
  pages: Page[] = [];
  fields: ExtractedField[] = [];
  classification!: Classification;
  types = TYPES;
  specialties = SPECIALTIES;
  label = label;
  ngOnInit() {
    this.pages = structuredClone(
      this.result.content?.pages ?? [
        {
          page: 1,
          text: "",
          method: "human_corrected",
          engine: null,
          uncertain: false,
        },
      ],
    );
    this.fields = structuredClone(this.result.extraction?.fields ?? []);
    this.classification = structuredClone(
      this.result.classification ?? {
        document_type: "UNKNOWN",
        specialty: "UNKNOWN",
        reason: "",
        evidence: { page: 1, quote: "" },
      },
    );
    if (!this.classification.evidence) this.classification.evidence = { page: 1, quote: "" };
  }
  addField() {
    this.fields.push({
      name: "",
      value: "",
      unit: null,
      evidence: { page: 1, quote: "" },
    });
  }
  async submit() {
    if (!this.confirmed || !this.notes.trim() || this.busy()) return;
    this.busy.set(true);
    this.error.set("");
    try {
      const body: Record<string, unknown> = {
        action: this.action,
        reviewer: "superadmin-local",
        notes: this.notes.trim(),
        confirmed_source_review: true,
      };
      if (this.action === "CORRECT") {
        body["content"] = { pages: this.pages };
        body["classification"] = this.classification;
        body["extraction"] = {
          fields: this.fields.map((f) => ({
            ...f,
            unit: f.unit?.trim() || null,
          })),
        };
      }
      await this.api.review(this.documentId, body);
      this.completed.emit();
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }
}
