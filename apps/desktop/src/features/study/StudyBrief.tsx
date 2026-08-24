import { AnalysisApiError, type AnalysisApi } from "../../api/client";
import type { MethodologyExtraction, StudyBrief as StudyBriefDto, StudyDesign } from "../../api/types";
import { useState } from "react";

interface StudyBriefProps {
  value: StudyBriefDto;
  onChange(value: StudyBriefDto): void;
  language: "en" | "tr";
  api?: AnalysisApi;
}

const KNOWN_ERROR_CODES = ["no_extractable_text", "unsupported_format", "file_too_large", "unreadable_document"] as const;
type KnownErrorCode = (typeof KNOWN_ERROR_CODES)[number];

function toKnownErrorCode(error: unknown): KnownErrorCode {
  // Server 422s carry "methodology_intake_failed:<code>" as the structured
  // AnalysisApiError.code (never in .message, which stays generic — see
  // client.ts responseError()). The locally-thrown "methodology_document_not_selected"
  // has no colon and simply fails the lookup below, landing on the same safe
  // fallback as any other code this UI does not recognize.
  const raw = error instanceof AnalysisApiError ? (error.code.split(":").at(-1) ?? "") : "";
  return (KNOWN_ERROR_CODES as readonly string[]).includes(raw) ? (raw as KnownErrorCode) : "unreadable_document";
}

const text = {
  en: {
    eyebrow: "01 / Scientific intent",
    title: "Study brief",
    intro: "Describe the clinical question before selecting a method. Your inputs remain editable until the plan is approved.",
    projectTitle: "Project title",
    projectPlaceholder: "e.g. Thirty-day blood pressure response",
    question: "Research question",
    questionPlaceholder: "What association or difference should the analysis estimate?",
    hypothesis: "Hypothesis",
    hypothesisPlaceholder: "State the expected direction without implying causality.",
    design: "Study design",
    outcomes: "Outcome variables",
    exposures: "Exposure variables",
    covariates: "Covariates",
    listHelp: "Use commas to separate variable names.",
    note: "The analysis plan will use the confirmed design and variable roles. Automated guidance supports, but does not replace, qualified statistical review.",
    upload: "Import methodology document",
    uploadHelp: "Word, PDF, text or markdown. Fields below are filled as suggestions you can change.",
    proposed: "from document",
    truncated: "The document was long, so only its first part was read.",
    noSection: "No methods section was found; the beginning of the document was used.",
    errors: {
      no_extractable_text: "This document has no readable text. A scanned PDF must be converted to text first — choose the file again once it has text.",
      unsupported_format: "This file type is not supported. Use Word, PDF, text or markdown, then choose the file again.",
      file_too_large: "This file is too large to read. Choose a smaller file.",
      unreadable_document: "This document could not be read. Choose the file again.",
    },
  },
  tr: {
    eyebrow: "01 / Bilimsel amaç",
    title: "Çalışma özeti",
    intro: "Bir yöntem seçmeden önce klinik soruyu tanımlayın. Plan onaylanana kadar girdiler düzenlenebilir.",
    projectTitle: "Proje başlığı",
    projectPlaceholder: "örn. Otuz günlük kan basıncı yanıtı",
    question: "Araştırma sorusu",
    questionPlaceholder: "Analiz hangi ilişkiyi veya farkı tahmin etmeli?",
    hypothesis: "Hipotez",
    hypothesisPlaceholder: "Nedensellik ima etmeden beklenen yönü belirtin.",
    design: "Çalışma tasarımı",
    outcomes: "Sonuç değişkenleri",
    exposures: "Maruziyet değişkenleri",
    covariates: "Kovaryatlar",
    listHelp: "Değişken adlarını virgülle ayırın.",
    note: "Analiz planı onaylanmış tasarım ve değişken rollerini kullanır. Otomatik rehberlik, yetkin istatistik incelemesini destekler ancak onun yerine geçmez.",
    upload: "Metodoloji dokümanı yükle",
    uploadHelp: "Word, PDF, metin veya markdown. Aşağıdaki alanlar öneri olarak doldurulur, değiştirebilirsiniz.",
    proposed: "dokümandan",
    truncated: "Doküman uzun olduğu için yalnızca ilk kısmı okundu.",
    noSection: "Yöntem bölümü bulunamadı; dokümanın başı kullanıldı.",
    errors: {
      no_extractable_text: "Bu dokümanda okunabilir metin yok. Taranmış bir PDF önce metne çevrilmelidir — metne çevirdikten sonra dosyayı yeniden seçin.",
      unsupported_format: "Bu dosya türü desteklenmiyor. Word, PDF, metin veya markdown kullanın ve dosyayı yeniden seçin.",
      file_too_large: "Bu dosya okunamayacak kadar büyük. Daha küçük bir dosya seçin.",
      unreadable_document: "Bu doküman okunamadı. Dosyayı yeniden seçin.",
    },
  },
} as const;

const designs: Array<{ value: StudyDesign; en: string; tr: string }> = [
  { value: "cross_sectional", en: "Cross-sectional", tr: "Kesitsel" },
  { value: "cohort", en: "Cohort", tr: "Kohort" },
  { value: "case_control", en: "Case–control", tr: "Olgu–kontrol" },
  { value: "trial", en: "Clinical trial", tr: "Klinik araştırma" },
  { value: "repeated", en: "Repeated measures", tr: "Tekrarlı ölçümler" },
];

function listValue(value?: string[]): string {
  return value?.join(", ") ?? "";
}

function parseList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function StudyBrief({ value, onChange, language, api }: StudyBriefProps) {
  const copy = text[language];
  const update = <Key extends keyof StudyBriefDto>(key: Key, next: StudyBriefDto[Key]) => {
    onChange({ ...value, [key]: next });
  };

  const [documentName, setDocumentName] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<MethodologyExtraction | null>(null);
  const [failure, setFailure] = useState<KnownErrorCode | null>(null);

  const importDocument = async () => {
    if (!api?.selectMethodologyDocument || !api.extractMethodology) return;
    setFailure(null);
    try {
      const name = await api.selectMethodologyDocument();
      if (!name) return;
      setDocumentName(name);
      const result = await api.extractMethodology();
      setExtraction(result);
      if (result.brief.design) {
        update("design", result.brief.design.value as StudyDesign);
      }
    } catch (error) {
      // Ruling 1: extractMethodology() clears its capability reference before
      // sending, so ANY failure here — including a transient one — leaves the
      // token dead. The copy for every code below tells the user to choose
      // the file again, never to just "try again".
      setFailure(toKnownErrorCode(error));
      setDocumentName(null);
      setExtraction(null);
    }
  };

  return (
    <section className="task-card" aria-labelledby="study-title">
      <header className="task-heading">
        <p className="eyebrow">{copy.eyebrow}</p>
        <h1 id="study-title">{copy.title}</h1>
        <p className="lede">{copy.intro}</p>
      </header>

      <div className="drop-panel">
        <div className="workbook-glyph" aria-hidden="true">DOC</div>
        <div>
          {documentName ? <p className="file-name">{documentName}</p> : null}
          <p className="form-help" id="methodology-upload-help">{copy.uploadHelp}</p>
          {extraction?.truncated ? <p className="warning-line">{copy.truncated}</p> : null}
          {extraction?.warnings.includes("no_method_section") ? <p className="warning-line">{copy.noSection}</p> : null}
        </div>
        <button
          type="button"
          className="primary-action"
          aria-describedby="methodology-upload-help"
          onClick={() => void importDocument()}
        >
          {copy.upload}
        </button>
      </div>
      {failure ? (
        <div className="error-panel" role="alert">
          <span aria-hidden="true">!</span>
          <p>{copy.errors[failure]}</p>
        </div>
      ) : null}

      <form className="study-form" onSubmit={(event) => event.preventDefault()}>
        <div className="field field-wide">
          <label htmlFor="project-title">{copy.projectTitle}</label>
          <input
            id="project-title"
            value={value.title}
            onChange={(event) => update("title", event.target.value)}
            placeholder={copy.projectPlaceholder}
          />
        </div>
        <div className="field field-wide">
          <label htmlFor="research-question">{copy.question}</label>
          <textarea
            id="research-question"
            required
            rows={3}
            value={value.question}
            onChange={(event) => update("question", event.target.value)}
            placeholder={copy.questionPlaceholder}
          />
        </div>
        <div className="field field-wide">
          <label htmlFor="hypothesis">{copy.hypothesis}</label>
          <textarea
            id="hypothesis"
            required
            rows={3}
            value={value.hypothesis}
            onChange={(event) => update("hypothesis", event.target.value)}
            placeholder={copy.hypothesisPlaceholder}
          />
        </div>
        <div className="field">
          <label htmlFor="study-design">
            {copy.design}
            {extraction?.brief.design ? (
              <span className="proposal-badge" title={extraction.brief.design.evidence ?? ""}>
                {copy.proposed}
              </span>
            ) : null}
          </label>
          <select id="study-design" value={value.design} onChange={(event) => update("design", event.target.value as StudyDesign)}>
            {designs.map((design) => <option key={design.value} value={design.value}>{design[language]}</option>)}
          </select>
          {extraction?.brief.design?.evidence ? (
            <p className="form-help evidence-quote">{extraction.brief.design.evidence}</p>
          ) : null}
        </div>
        <div className="field">
          <label htmlFor="outcomes">{copy.outcomes}</label>
          <input id="outcomes" value={listValue(value.outcome_variables)} onChange={(event) => update("outcome_variables", parseList(event.target.value))} aria-describedby="variable-list-help" />
        </div>
        <div className="field">
          <label htmlFor="exposures">{copy.exposures}</label>
          <input id="exposures" value={listValue(value.exposure_variables)} onChange={(event) => update("exposure_variables", parseList(event.target.value))} aria-describedby="variable-list-help" />
        </div>
        <div className="field">
          <label htmlFor="covariates">{copy.covariates}</label>
          <input id="covariates" value={listValue(value.covariates)} onChange={(event) => update("covariates", parseList(event.target.value))} aria-describedby="variable-list-help" />
        </div>
        <p id="variable-list-help" className="form-help field-wide">{copy.listHelp}</p>
      </form>

      <aside className="evidence-note">
        <span aria-hidden="true" className="note-mark">i</span>
        <p>{copy.note}</p>
      </aside>
    </section>
  );
}
