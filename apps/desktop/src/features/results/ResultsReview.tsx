import type { AnalysisResult } from "../../api/types";

interface ResultsReviewProps {
  language: "en" | "tr";
  results: AnalysisResult[];
}

const copy = {
  en: { eyebrow: "05 / Verified output", title: "Results", intro: "Review the approved analysis output before exporting a journal-neutral Results section.", estimate: "Estimate", interval: "95% CI", p: "p value", effect: "Effect size", provenance: "Analysis provenance", planVersion: "plan v", between: "to", warnings: "Warnings requiring review", warningLabel: "Warning requiring review", warningDetail: "This result includes a warning that should be reviewed before release." },
  tr: { eyebrow: "05 / Doğrulanmış çıktı", title: "Sonuçlar", intro: "Dergiden bağımsız Sonuçlar bölümünü dışa aktarmadan önce onaylanmış analiz çıktısını inceleyin.", estimate: "Tahmin", interval: "%95 GA", p: "p değeri", effect: "Etki büyüklüğü", provenance: "Analiz kökeni", planVersion: "plan s", between: "ile", warnings: "Gözden geçirilecek uyarılar", warningLabel: "Gözden geçirilmesi gereken uyarı", warningDetail: "Bu sonuç yayımlamadan önce incelenmesi gereken bir uyarı içerir." },
} as const;

function value(number: number | null): string { return number === null ? "—" : number.toFixed(2); }

export function ResultsReview({ language, results }: ResultsReviewProps) {
  const text = copy[language];
  return <section className="task-card" aria-labelledby="results-title">
    <header className="task-heading"><p className="eyebrow">{text.eyebrow}</p><h1 id="results-title">{text.title}</h1><p className="lede">{text.intro}</p></header>
    {results.map((result) => <article className="result-card" key={result.id}>
      <h2>{result.method}</h2>
      <dl className="result-metrics"><div><dt>{text.estimate}</dt><dd>{value(result.estimate)}</dd></div><div><dt>{text.interval}</dt><dd>{value(result.confidence_interval.lower)} {text.between} {value(result.confidence_interval.upper)}</dd></div><div><dt>{text.p}</dt><dd>{value(result.p_value)}</dd></div><div><dt>{text.effect}</dt><dd>{result.effect_size.name} {value(result.effect_size.value)}</dd></div></dl>
      {result.warnings.length > 0 ? <section className="result-warning" role="note" aria-label={text.warningLabel}><span aria-hidden="true">!</span><div><strong>{text.warnings}</strong><p>{text.warningDetail}</p><ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div></section> : null}
      <p className="provenance"><strong>{text.provenance}:</strong> {result.provenance.data_fingerprint.slice(0, 12)} · {text.planVersion}{result.provenance.plan_version} · n = {result.n}</p>
    </article>)}
  </section>;
}
