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
  en: { navigation: "Analysis workflow", skip: "Skip to active task", language: "Interface language", offline: "Offline · data stays on this Mac", inspector: "Scientific inspector", methodNote: "METHOD NOTE", inspectorTitle: "Review before release", inspectorText: "Results remain observational unless the approved design and estimand justify a causal interpretation.", mode: "Mode", localOnly: "Local only", auditTrail: "Audit trail", enabled: "Enabled", inspectorWarnings: "Warnings to review", running: "Running approved analysis", progress: "Analysis progress", cancelled: "Analysis cancelled. No partial results were accepted.", ready: "Ready for a reviewed analysis.", runEyebrow: "04 / Reproducible execution", cancel: "Cancel analysis", failures: { plan: { title: "Analysis plan could not be completed", detail: "The local service did not return a complete, validated plan.", retry: "Retry plan generation" }, analysis: { title: "Analysis could not be completed", detail: "The local service did not return a complete, validated result.", retry: "Retry analysis" }, export: { title: "Word report could not be completed", detail: "The local service could not write a complete, validated Word report.", retry: "Retry Word export" } }, stages: { study: "Study brief", data: "Data & variables", plan: "Analysis plan", run: "Run & diagnose", results: "Results review", report: "Word report" } },
  tr: { navigation: "Analiz iş akışı", skip: "Etkin göreve atla", language: "Arayüz dili", offline: "Çevrimdışı · veriler bu Mac'te kalır", inspector: "Bilimsel denetçi", methodNote: "YÖNTEM NOTU", inspectorTitle: "Yayımlamadan önce inceleyin", inspectorText: "Onaylanan tasarım ve tahmin edilen değer nedensel bir yorumu desteklemedikçe sonuçlar gözlemsel kalır.", mode: "Kip", localOnly: "Yerel kullanım", auditTrail: "Denetim kaydı", enabled: "Etkin", inspectorWarnings: "Gözden geçirilecek uyarılar", running: "Onaylanmış analiz çalışıyor", progress: "Analiz ilerlemesi", cancelled: "Analiz iptal edildi. Kısmi sonuç kabul edilmedi.", ready: "İncelenmiş analiz için hazır.", runEyebrow: "04 / Tekrarlanabilir yürütme", cancel: "Analizi iptal et", failures: { plan: { title: "Analiz planı tamamlanamadı", detail: "Yerel hizmet eksiksiz ve doğrulanmış bir plan döndürmedi.", retry: "Plan oluşturmayı yeniden dene" }, analysis: { title: "Analiz tamamlanamadı", detail: "Yerel hizmet eksiksiz ve doğrulanmış bir sonuç döndürmedi.", retry: "Analizi yeniden dene" }, export: { title: "Word raporu tamamlanamadı", detail: "Yerel hizmet eksiksiz ve doğrulanmış bir Word raporu yazamadı.", retry: "Word dışa aktarımını yeniden dene" } }, stages: { study: "Çalışma özeti", data: "Veri ve değişkenler", plan: "Analiz planı", run: "Çalıştır ve tanıla", results: "Sonuçları incele", report: "Word raporu" } },
} as const;

const steps: WorkflowStep[] = ["study", "data", "plan", "run", "results", "report"];

type FailedOperation = "plan" | "analysis" | "export";

function ErrorBanner({ language, operation, onRetry }: { language: Language; operation: FailedOperation; onRetry(): void }) {
  const text = labels[language];
  const failure = text.failures[operation];
  return <div className="error-panel" role="alert"><span aria-hidden="true">!</span><div><strong>{failure.title}</strong><p>{failure.detail}</p></div><button type="button" className="secondary-action" onClick={onRetry}>{failure.retry}</button></div>;
}

export function App({ api }: { api: AnalysisApi }) {
  const project = useProjectStore();
  const [approved, setApproved] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [running, setRunning] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [failedOperation, setFailedOperation] = useState<FailedOperation | null>(null);
  const [exporting, setExporting] = useState(false);
  const [savedPath, setSavedPath] = useState<string | null>(null);
  const runId = useRef(0);
  const text = labels[project.language];

  useEffect(() => { document.documentElement.lang = project.language; }, [project.language]);

  const requestPlan = async () => {
    setPlanning(true); setFailedOperation(null); setApproved(false);
    try { project.setPlan(await api.createPlan({ ...project.brief, language: project.language })); }
    catch { setFailedOperation("plan"); }
    finally { setPlanning(false); }
  };

  const goTo = (step: WorkflowStep) => {
    if ((step === "results" || step === "report") && project.results.length === 0) return;
    project.setActiveStep(step);
    if (step === "plan" && !project.plan && !planning) void requestPlan();
  };

  const runAnalysis = async () => {
    if (!project.plan || !approved) return;
    const current = ++runId.current;
    setRunning(true); setCancelled(false); setFailedOperation(null); project.setActiveStep("run");
    try {
      const results = await api.runAnalysis(project.plan);
      if (runId.current !== current) return;
      project.setResults(results); project.setActiveStep("results");
    } catch {
      if (runId.current === current) setFailedOperation("analysis");
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
    if (project.results.length === 0) return;
    setExporting(true); setSavedPath(null); setFailedOperation(null);
    try { setSavedPath(await api.exportReport(project.results, project.language)); }
    catch { setFailedOperation("export"); }
    finally { setExporting(false); }
  };

  const retryFailedOperation = () => {
    if (failedOperation === "plan") void requestPlan();
    if (failedOperation === "analysis") void runAnalysis();
    if (failedOperation === "export") void exportReport();
  };
  const completedResults = project.results.length > 0;
  const inspectorWarnings = [...new Set([
    ...(project.plan?.warnings ?? []),
    ...(project.plan?.items.flatMap((item) => item.warnings) ?? []),
    ...project.results.flatMap((result) => result.warnings),
  ])];

  return <div className="app-shell">
    <a className="skip-link" href="#workspace">{text.skip}</a>
    <aside className="workflow-rail"><div className="brand"><span aria-hidden="true">BS</span><strong>BioStat Studio</strong></div><p className="offline-pill"><span aria-hidden="true">●</span>{text.offline}</p><nav aria-label={text.navigation}><ol>{steps.map((step, index) => { const locked = (step === "results" || step === "report") && !completedResults; return <li key={step}><button type="button" disabled={locked} aria-current={project.activeStep === step ? "step" : undefined} className={project.activeStep === step ? "active" : ""} onClick={() => goTo(step)}><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{text.stages[step]}</button></li>; })}</ol></nav><label className="language-control"><span>{text.language}</span><select aria-label={text.language} value={project.language} onChange={(event) => project.setLanguage(event.target.value as Language)}><option value="en">English</option><option value="tr">Türkçe</option></select></label></aside>
    <main id="workspace" tabIndex={-1}>
      {failedOperation ? <ErrorBanner language={project.language} operation={failedOperation} onRetry={retryFailedOperation} /> : null}
      {project.activeStep === "study" ? <StudyBrief value={project.brief} onChange={project.setBrief} language={project.language} /> : null}
      {project.activeStep === "data" ? <DataIntake api={api} dataFile={project.dataFile} onFile={project.setDataFile} language={project.language} /> : null}
      {project.activeStep === "plan" ? <PlanReview language={project.language} plan={project.plan} loading={planning} approved={approved} onApproval={setApproved} onRun={() => void runAnalysis()} /> : null}
      {project.activeStep === "run" ? <section className="task-card run-card" aria-labelledby="run-title"><p className="eyebrow">{text.runEyebrow}</p><h1 id="run-title">{text.stages.run}</h1>{running ? <><p role="status">{text.running}</p><progress aria-label={text.progress} aria-valuenow={42} value={42} max={100}>42%</progress><button type="button" className="secondary-action" onClick={() => void cancel()}>{text.cancel}</button></> : cancelled ? <p role="status">{text.cancelled}</p> : <p className="loading-note">{text.ready}</p>}</section> : null}
      {project.activeStep === "results" ? <ResultsReview language={project.language} results={project.results} /> : null}
      {project.activeStep === "report" ? <ReportExport language={project.language} exporting={exporting} canExport={completedResults} savedPath={savedPath} onExport={() => void exportReport()} /> : null}
    </main>
    <aside className="scientific-inspector" aria-label={text.inspector}><p className="eyebrow">{text.methodNote}</p><h2>{text.inspectorTitle}</h2><p>{text.inspectorText}</p><dl><div><dt>{text.mode}</dt><dd>{text.localOnly}</dd></div><div><dt>{text.auditTrail}</dt><dd>{text.enabled}</dd></div></dl>{inspectorWarnings.length > 0 ? <section className="inspector-warnings" aria-labelledby="inspector-warnings-title"><h3 id="inspector-warnings-title">{text.inspectorWarnings}</h3><ul>{inspectorWarnings.map((warning) => <li key={warning}><span aria-hidden="true">!</span>{warning}</li>)}</ul></section> : null}</aside>
  </div>;
}
