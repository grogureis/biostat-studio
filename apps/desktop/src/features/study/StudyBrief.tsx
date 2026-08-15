import type { StudyBrief as StudyBriefDto, StudyDesign } from "../../api/types";

interface StudyBriefProps {
  value: StudyBriefDto;
  onChange(value: StudyBriefDto): void;
  language: "en" | "tr";
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

export function StudyBrief({ value, onChange, language }: StudyBriefProps) {
  const copy = text[language];
  const update = <Key extends keyof StudyBriefDto>(key: Key, next: StudyBriefDto[Key]) => {
    onChange({ ...value, [key]: next });
  };

  return (
    <section className="task-card" aria-labelledby="study-title">
      <header className="task-heading">
        <p className="eyebrow">{copy.eyebrow}</p>
        <h1 id="study-title">{copy.title}</h1>
        <p className="lede">{copy.intro}</p>
      </header>

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
          <label htmlFor="study-design">{copy.design}</label>
          <select id="study-design" value={value.design} onChange={(event) => update("design", event.target.value as StudyDesign)}>
            {designs.map((design) => <option key={design.value} value={design.value}>{design[language]}</option>)}
          </select>
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
