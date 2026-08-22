import type { AnalysisPlan } from "../../api/types";

interface PlanReviewProps {
  language: "en" | "tr";
  plan: AnalysisPlan | null;
  approved: boolean;
  loading: boolean;
  onApproval(next: boolean): void;
  onRun(): void;
  onAlternative(itemId: string, method: string): void;
}

const copy = {
  en: {
    eyebrow: "03 / Decision record",
    title: "Analysis plan",
    intro: "Review the estimand, assumptions, and the documented alternative before executing the approved primary method.",
    loading: "Preparing an analysis plan from the study brief…",
    approve: "Approve this plan",
    run: "Run analysis",
    blocked: "Resolve the blocking items before approving this plan.",
    assumptions: "Assumptions to review",
    alternative: "Documented alternative (not automatically executed)",
    useAlternative: "Use this alternative (regenerate plan)",
    alternativeHelp: "Switching regenerates the plan and requires a new approval.",
  },
  tr: {
    eyebrow: "03 / Karar kaydı",
    title: "Analiz planı",
    intro: "Onaylanan birincil yöntemi yürütmeden önce tahmin edilecek değeri, varsayımları ve belgelenmiş alternatifi gözden geçirin.",
    loading: "Çalışma özetinden analiz planı hazırlanıyor…",
    approve: "Bu planı onayla",
    run: "Analizi çalıştır",
    blocked: "Bu planı onaylamadan önce engelleyici maddeleri çözün.",
    assumptions: "Gözden geçirilecek varsayımlar",
    alternative: "Belgelenmiş alternatif (otomatik yürütülmez)",
    useAlternative: "Bu alternatifi kullan (planı yeniden oluştur)",
    alternativeHelp: "Geçiş planı yeniden oluşturur ve yeni bir onay gerektirir.",
  },
} as const;

export function PlanReview({ language, plan, approved, loading, onApproval, onRun, onAlternative }: PlanReviewProps) {
  const text = copy[language];
  const blocking = plan?.blocking_errors ?? [];

  return (
    <section className="task-card" aria-labelledby="plan-title">
      <header className="task-heading">
        <p className="eyebrow">{text.eyebrow}</p>
        <h1 id="plan-title">{text.title}</h1>
        <p className="lede">{text.intro}</p>
      </header>
      {loading && !plan ? <p className="loading-note" role="status">{text.loading}</p> : null}
      {plan?.items.map((item) => (
        <article className="plan-item" key={item.id}>
          <div className="plan-kicker">{item.estimand}</div>
          <h2>{item.method}</h2>
          <p>{item.rationale}</p>
          <div className="plan-detail-grid">
            <div><h3>{text.assumptions}</h3><ul>{item.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></div>
            {item.robust_alternative ? <div><h3>{text.alternative}</h3><p>{item.robust_alternative}</p><button type="button" className="secondary-action" disabled={loading} onClick={() => onAlternative(item.id, item.robust_alternative as string)}>{text.useAlternative}</button><p className="microcopy">{text.alternativeHelp}</p></div> : null}
          </div>
          {item.warnings.map((warning) => <p className="warning-line" key={warning}><span aria-hidden="true">!</span>{warning}</p>)}
        </article>
      ))}
      {blocking.length > 0 ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{text.blocked}</p></div> : null}
      <footer className="approval-bar">
        <label className="approval-check"><input type="checkbox" checked={approved} onChange={(event) => onApproval(event.target.checked)} disabled={blocking.length > 0} /> <span>{text.approve}</span></label>
        <button type="button" className="primary-action" onClick={onRun} disabled={!approved || !plan || loading}>{text.run}</button>
      </footer>
    </section>
  );
}
