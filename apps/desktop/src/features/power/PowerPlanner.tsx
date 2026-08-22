import { useState } from "react";

import type { AnalysisApi } from "../../api/client";
import type { PowerAnalysis, PowerResponse } from "../../api/types";

interface PowerPlannerProps {
  api: AnalysisApi;
  language: "en" | "tr";
}

const copy = {
  en: {
    eyebrow: "07 / Planning calculator",
    title: "Power & sample size",
    intro:
      "Plan a future study size a priori. This calculator uses no imported data and does not change the analysis workflow or its audit trail.",
    analysis: "Statistical test",
    analyses: {
      two_sample_t: "Two-sample t test (Cohen's d)",
      paired_t: "Paired t test (Cohen's dz)",
      one_way_anova: "One-way ANOVA (Cohen's f)",
      two_proportions: "Two independent proportions",
      correlation: "Correlation (Pearson's r)",
    },
    solveFor: "Solve for",
    solveSample: "Required sample size",
    solvePower: "Achieved power",
    alpha: "Type I error (alpha)",
    effect: "Standardized effect size",
    proportionOne: "Proportion in group 1",
    proportionTwo: "Proportion in group 2",
    targetPower: "Target power",
    sampleSizes: {
      two_sample_t: "Sample size per group",
      paired_t: "Number of pairs",
      one_way_anova: "Total sample size",
      two_proportions: "Sample size per group",
      correlation: "Number of paired observations",
    },
    groups: "Number of groups",
    compute: "Compute",
    resultSample: "Required sample size",
    resultPower: "Achieved power",
    perGroup: "per group",
    pairs: "pairs",
    total: "total",
    achievedNote: "Achieved power at the rounded allocation",
    failure: "The calculation could not be completed. Review the inputs.",
    note: "Deterministic a-priori planning support; it is not evidence about any imported dataset and does not replace qualified statistical review.",
  },
  tr: {
    eyebrow: "07 / Planlama hesaplayıcısı",
    title: "Güç ve örneklem büyüklüğü",
    intro:
      "Gelecekteki bir çalışmanın boyutunu önsel olarak planlayın. Bu hesaplayıcı içe aktarılmış veri kullanmaz; analiz iş akışını ve denetim kaydını değiştirmez.",
    analysis: "İstatistiksel test",
    analyses: {
      two_sample_t: "İki örneklem t testi (Cohen d)",
      paired_t: "Eşleştirilmiş t testi (Cohen dz)",
      one_way_anova: "Tek yönlü ANOVA (Cohen f)",
      two_proportions: "İki bağımsız oran",
      correlation: "Korelasyon (Pearson r)",
    },
    solveFor: "Hesaplanacak değer",
    solveSample: "Gerekli örneklem büyüklüğü",
    solvePower: "Ulaşılan güç",
    alpha: "Tip I hata (alfa)",
    effect: "Standartlaştırılmış etki büyüklüğü",
    proportionOne: "1. grup oranı",
    proportionTwo: "2. grup oranı",
    targetPower: "Hedef güç",
    sampleSizes: {
      two_sample_t: "Grup başına örneklem",
      paired_t: "Çift sayısı",
      one_way_anova: "Toplam örneklem",
      two_proportions: "Grup başına örneklem",
      correlation: "Eşleştirilmiş gözlem sayısı",
    },
    groups: "Grup sayısı",
    compute: "Hesapla",
    resultSample: "Gerekli örneklem büyüklüğü",
    resultPower: "Ulaşılan güç",
    perGroup: "grup başına",
    pairs: "çift",
    total: "toplam",
    achievedNote: "Yuvarlanmış dağılımda ulaşılan güç",
    failure: "Hesaplama tamamlanamadı. Girdileri gözden geçirin.",
    note: "Belirlenimci önsel planlama desteğidir; içe aktarılmış herhangi bir veri kümesi hakkında kanıt değildir ve yetkin istatistik incelemesinin yerine geçmez.",
  },
} as const;

const analyses: PowerAnalysis[] = [
  "two_sample_t",
  "paired_t",
  "one_way_anova",
  "two_proportions",
  "correlation",
];

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

export function PowerPlanner({ api, language }: PowerPlannerProps) {
  const text = copy[language];
  const [analysis, setAnalysis] = useState<PowerAnalysis>("two_sample_t");
  const [solveFor, setSolveFor] = useState<"power" | "sample_size">("sample_size");
  const [alpha, setAlpha] = useState("0.05");
  const [effectSize, setEffectSize] = useState("0.5");
  const [proportionOne, setProportionOne] = useState("0.6");
  const [proportionTwo, setProportionTwo] = useState("0.4");
  const [targetPower, setTargetPower] = useState("0.8");
  const [sampleSize, setSampleSize] = useState("64");
  const [groups, setGroups] = useState("3");
  const [computing, setComputing] = useState(false);
  const [failed, setFailed] = useState(false);
  const [result, setResult] = useState<PowerResponse | null>(null);

  const compute = async () => {
    setComputing(true);
    setFailed(false);
    setResult(null);
    try {
      const response = await api.computePower({
        analysis,
        solve_for: solveFor,
        alpha: Number(alpha),
        ...(solveFor === "sample_size" ? { power: Number(targetPower) } : {}),
        ...(solveFor === "power" ? { sample_size: Number(sampleSize) } : {}),
        ...(analysis === "two_proportions"
          ? { proportion_one: Number(proportionOne), proportion_two: Number(proportionTwo) }
          : { effect_size: Number(effectSize) }),
        ...(analysis === "one_way_anova" ? { groups: Number(groups) } : {}),
      });
      setResult(response);
    } catch {
      setFailed(true);
    } finally {
      setComputing(false);
    }
  };

  const unitLabel = (unit: PowerResponse["sample_size_unit"]): string =>
    unit === "per_group" ? text.perGroup : unit === "pairs" ? text.pairs : text.total;

  return (
    <section className="task-card" aria-labelledby="power-title">
      <header className="task-heading">
        <p className="eyebrow">{text.eyebrow}</p>
        <h1 id="power-title">{text.title}</h1>
        <p className="lede">{text.intro}</p>
      </header>
      <div className="study-form">
        <div className="field">
          <label htmlFor="power-analysis">{text.analysis}</label>
          <select
            id="power-analysis"
            value={analysis}
            onChange={(event) => setAnalysis(event.target.value as PowerAnalysis)}
          >
            {analyses.map((value) => (
              <option key={value} value={value}>{text.analyses[value]}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="power-solve">{text.solveFor}</label>
          <select
            id="power-solve"
            value={solveFor}
            onChange={(event) => setSolveFor(event.target.value as "power" | "sample_size")}
          >
            <option value="sample_size">{text.solveSample}</option>
            <option value="power">{text.solvePower}</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="power-alpha">{text.alpha}</label>
          <input id="power-alpha" type="number" step="0.01" min="0.0001" max="0.9999" value={alpha} onChange={(event) => setAlpha(event.target.value)} />
        </div>
        {analysis === "two_proportions" ? (
          <>
            <div className="field">
              <label htmlFor="power-p1">{text.proportionOne}</label>
              <input id="power-p1" type="number" step="0.01" min="0.01" max="0.99" value={proportionOne} onChange={(event) => setProportionOne(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="power-p2">{text.proportionTwo}</label>
              <input id="power-p2" type="number" step="0.01" min="0.01" max="0.99" value={proportionTwo} onChange={(event) => setProportionTwo(event.target.value)} />
            </div>
          </>
        ) : (
          <div className="field">
            <label htmlFor="power-effect">{text.effect}</label>
            <input id="power-effect" type="number" step="0.05" value={effectSize} onChange={(event) => setEffectSize(event.target.value)} />
          </div>
        )}
        {solveFor === "sample_size" ? (
          <div className="field">
            <label htmlFor="power-target">{text.targetPower}</label>
            <input id="power-target" type="number" step="0.05" min="0.05" max="0.99" value={targetPower} onChange={(event) => setTargetPower(event.target.value)} />
          </div>
        ) : (
          <div className="field">
            <label htmlFor="power-n">{text.sampleSizes[analysis]}</label>
            <input id="power-n" type="number" step="1" min="2" value={sampleSize} onChange={(event) => setSampleSize(event.target.value)} />
          </div>
        )}
        {analysis === "one_way_anova" ? (
          <div className="field">
            <label htmlFor="power-groups">{text.groups}</label>
            <input id="power-groups" type="number" step="1" min="2" value={groups} onChange={(event) => setGroups(event.target.value)} />
          </div>
        ) : null}
      </div>
      <footer className="approval-bar">
        <button type="button" className="primary-action" disabled={computing} onClick={() => void compute()}>
          {text.compute}
        </button>
      </footer>
      {failed ? (
        <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{text.failure}</p></div>
      ) : null}
      {result ? (
        <div className="result-card" role="status">
          {result.solve_for === "sample_size" ? (
            <>
              <h2>{text.resultSample}</h2>
              <p>
                {result.total_rounded !== null
                && result.per_group_rounded !== null
                && result.total_rounded !== result.per_group_rounded
                  ? `n = ${result.per_group_rounded} ${text.perGroup} (${text.total}: ${result.total_rounded})`
                  : `n = ${result.per_group_rounded ?? "—"} ${unitLabel(result.sample_size_unit)}`}
              </p>
              <p className="microcopy">{`${text.achievedNote}: ${formatPercent(result.achieved_power)}`}</p>
            </>
          ) : (
            <>
              <h2>{text.resultPower}</h2>
              <p>{formatPercent(result.power)}</p>
            </>
          )}
        </div>
      ) : null}
      <div className="evidence-note"><span className="note-mark" aria-hidden="true">i</span><p>{text.note}</p></div>
    </section>
  );
}
