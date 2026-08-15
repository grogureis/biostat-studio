import { useEffect, useRef, useState } from "react";
import type { AnalysisApi } from "./api/client";
import type { AnalysisResult, Language } from "./api/types";
import { DataIntake } from "./features/data/DataIntake";
import { PlanReview } from "./features/plan/PlanReview";
import { useProjectStore, type WorkflowStep } from "./features/project/store";
import { ReportExport } from "./features/report/ReportExport";
import { ResultsReview } from "./features/results/ResultsReview";
import { StudyBrief } from "./features/study/StudyBrief";
import "./styles/clinical-calm.css";

const labels = {
  en: { navigation: "Analysis workflow", skip: "Skip to active task", language: "Interface language", offline: "Offline · data stays on this Mac", inspector: "Scientific inspector", inspectorTitle: "Review before release", inspectorText: "Results remain observational unless the approved design and estimand justify a causal interpretation.", running: "Running approved analysis", cancelled: "Analysis cancelled. No partial results were accepted.", failed: "Analysis could not be completed", retry: "Retry analysis", cancel: "Cancel analysis", stages: { study: "Study brief", data: "Data & variables", plan: "Analysis plan", run: "Run & diagnose", results: "Results review", report: "Word report" } },
  tr: { navigation: "Analiz iş akışı", skip: "Etkin göreve atla", language: "Arayüz dili", offline: "Çevrimdışı · veriler bu Mac'te kalır", inspector: "Bilimsel denetçi", inspectorTitle: "Yayımlamadan önce inceleyin", inspectorText: "Onaylanan tasarım ve tahmin edilen değer nedensel bir yorumu desteklemedikçe sonuçlar gözlemsel kalır.", running: "Onaylanmış analiz çalışıyor", cancelled: "Analiz iptal edildi. Kısmi sonuç kabul edilmedi.", failed: "Analiz tamamlanamadı", retry: "Analizi yeniden dene", cancel: "Analizi iptal et", stages: { study: "Çalışma özeti", data: "Veri ve değişkenler", plan: "Analiz planı", run: "Çalıştır ve tanıla", results: "Sonuçları incele", report: "Word raporu" } },
} as const;

const steps: WorkflowStep[] = ["study", "data", "plan", "run", "results", "report"];

function ErrorBanner({ language, onRetry }: { language: Language; onRetry(): void }) {
  const text = labels[language];
  return <div className="error-panel" role="alert"><span aria-hidden="true">!</span><div><strong>{text.failed}</strong><p>The local service did not return a complete, validated result.</p></div><button type="button" className="secondary-action" onClick={onRetry}>{text.retry}</button></div>;
}

export function App({ api }: { api: AnalysisApi }) {
  const project = useProjectStore();
  const [approved, setApproved] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [running, setRunning] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [analysisError, setAnalysisError] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [savedPath, setSavedPath] = useState<string | null>(null);
  const runId = useRef(0);
  const text = labels[project.language];

  useEffect(() => { document.documentElement.lang = project.language; }, [project.language]);

  const requestPlan = async () => {
    setPlanning(true); setAnalysisError(false); setApproved(false);
    try { project.setPlan(await api.createPlan({ ...project.brief, language: project.language })); }
    catch { setAnalysisError(true); }
    finally { setPlanning(false); }
  };

  const goTo = (step: WorkflowStep) => {
    project.setActiveStep(step);
    if (step === "plan" && !project.plan && !planning) void requestPlan();
  };

  const runAnalysis = async () => {
    if (!project.plan || !approved) return;
    const current = ++runId.current;
    setRunning(true); setCancelled(false); setAnalysisError(false); project.setActiveStep("run");
    try {
      const results = await api.runAnalysis(project.plan);
      if (runId.current !== current) return;
      project.setResults(results); project.setActiveStep("results");
    } catch {
      if (runId.current === current) setAnalysisError(true);
    } finally {
      if (runId.current === current) setRunning(false);
    }
  };

  const cancel = async () => {
    ++runId.current;
    await api.cancelAnalysis();
    setRunning(false); setCancelled(true); project.setResults([]);
  };

  const exportReport = async () => {
    setExporting(true); setSavedPath(null);
    try { setSavedPath(await api.exportReport(project.results, project.language)); }
    finally { setExporting(false); }
  };

  return <div className="app-shell">
    <a className="skip-link" href="#workspace">{text.skip}</a>
    <aside className="workflow-rail"><div className="brand"><span aria-hidden="true">BS</span><strong>BioStat Studio</strong></div><p className="offline-pill"><span aria-hidden="true">●</span>{text.offline}</p><nav aria-label={text.navigation}><ol>{steps.map((step, index) => <li key={step}><button type="button" aria-current={project.activeStep === step ? "step" : undefined} className={project.activeStep === step ? "active" : ""} onClick={() => goTo(step)}><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{text.stages[step]}</button></li>)}</ol></nav><label className="language-control"><span>{text.language}</span><select aria-label={text.language} value={project.language} onChange={(event) => project.setLanguage(event.target.value as Language)}><option value="en">English</option><option value="tr">Türkçe</option></select></label></aside>
    <main id="workspace" tabIndex={-1}>
      {analysisError ? <ErrorBanner language={project.language} onRetry={() => void runAnalysis()} /> : null}
      {project.activeStep === "study" ? <StudyBrief value={project.brief} onChange={project.setBrief} language={project.language} /> : null}
      {project.activeStep === "data" ? <DataIntake api={api} dataFile={project.dataFile} onFile={project.setDataFile} language={project.language} /> : null}
      {project.activeStep === "plan" ? <PlanReview language={project.language} plan={project.plan} loading={planning} approved={approved} onApproval={setApproved} onRun={() => void runAnalysis()} /> : null}
      {project.activeStep === "run" ? <section className="task-card run-card" aria-labelledby="run-title"><p className="eyebrow">04 / Reproducible execution</p><h1 id="run-title">{text.stages.run}</h1>{running ? <><p role="status">{text.running}</p><progress aria-label="Analysis progress" aria-valuenow={42} value={42} max={100}>42%</progress><button type="button" className="secondary-action" onClick={() => void cancel()}>{text.cancel}</button></> : cancelled ? <p role="status">{text.cancelled}</p> : <p className="loading-note">Ready for a reviewed analysis.</p>}</section> : null}
      {project.activeStep === "results" ? <ResultsReview language={project.language} results={project.results} /> : null}
      {project.activeStep === "report" ? <ReportExport language={project.language} exporting={exporting} savedPath={savedPath} onExport={() => void exportReport()} /> : null}
    </main>
    <aside className="scientific-inspector" aria-label={text.inspector}><p className="eyebrow">METHOD NOTE</p><h2>{text.inspectorTitle}</h2><p>{text.inspectorText}</p><dl><div><dt>Mode</dt><dd>Local only</dd></div><div><dt>Audit trail</dt><dd>Enabled</dd></div></dl></aside>
  </div>;
}
