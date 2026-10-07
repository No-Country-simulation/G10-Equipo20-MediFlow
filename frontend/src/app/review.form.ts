import { Component, EventEmitter, Input, Output, OnInit, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { Api } from "./api";
import { Classification, ExtractedField, Page, Result, label } from "./models";
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
  policyGroups = signal<Record<string, string[][]>>({});
  get types() { return this.api.catalog().types.map(item => item.code); }
  get specialties() { return this.api.catalog().specialties.map(item => item.code); }
  get requiredGroups() {
    const kind = this.classification?.document_type;
    const applied = this.result.quality?.policy;
    if (applied?.document_type === kind) return applied.required_groups;
    return this.policyGroups()[kind] ?? this.api.catalog().types.find(item => item.code === kind)?.required_groups ?? [];
  }
  async loadPolicy() {
    const kind = this.classification?.document_type;
    if (!kind || this.result.quality?.policy?.document_type === kind) return;
    try {
      const policy = await this.api.request<{required_groups: string[][]}>(`/document-policies/${kind}`);
      if (Array.isArray(policy.required_groups)) this.policyGroups.update(groups => ({...groups, [kind]: policy.required_groups}));
    } catch { /* Older results and unknown types use the catalog fallback. */ }
  }
  get suggestedFields() { return this.api.catalog().types.find(item => item.code === this.classification?.document_type)?.fields || []; }
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
        evidence: { page: this.pages[0]?.page ?? null, quote: "" },
      },
    );
    if (!this.classification.evidence) this.classification.evidence = { page: this.pages[0]?.page ?? null, quote: "" };
    void this.loadPolicy();
  }
  addField() {
    this.fields.push({
      name: "",
      value: "",
      unit: null,
      evidence: { page: this.pages[0]?.page ?? null, quote: "" },
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
            entity_id: f.entity_id?.trim() || null,
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
