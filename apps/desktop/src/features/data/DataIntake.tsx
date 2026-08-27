import { AnalysisApiError, type AnalysisApi } from "../../api/client";
import type { ConflictDto, DataProfile, MethodologyExtraction, RoleProposalDto, StudyBrief, VariableProposalResponse, VariableRole } from "../../api/types";
import { useEffect, useState } from "react";
import { methodLabel } from "../plan/methodLabels";

interface DataIntakeProps {
  api: AnalysisApi;
  dataFile: string | null;
  approved: boolean;
  language: "en" | "tr";
  brief?: StudyBrief;
  methodology?: MethodologyExtraction | null;
  onFile(path: string | null): void;
  onApproval(roles: VariableRole[]): Promise<void>;
}

const labels = {
  en: {
    eyebrow: "02 / Data provenance",
    title: "Data & variables",
    intro: "Import an immutable Excel workbook, then review variable roles and coding before planning.",
    import: "Import Excel",
    importing: "Importing Excel…",
    noFile: "No workbook selected",
    selected: "Selected workbook",
    approve: "Approve data structure",
    approved: "Data structure approved",
    approving: "Approving data structure…",
    approvalFailure: "Data structure approval could not be completed. Review the workbook and try again.",
    privacy: "Only the file name is shown here. The original workbook is never overwritten.",
    pickerFailure: "The workbook picker could not be opened. Try again.",
    profileFailure: "The Excel workbook could not be read. Check that it is a valid XLSX file and try again.",
    briefFailure: "Complete the required study-brief fields before importing Excel.",
    matchingFailure: "The workbook was read, but the project and variable suggestions could not be prepared. Review the study brief and try again.",
    profilingStatus: "Reading the Excel structure on this Mac…",
    projectStatus: "Excel is ready. Choose where to save the local BioStat project in the window that opens; then the local AI will match the methodology to the variables.",
    acceptRemaining: "Accept remaining clear variables",
    reviewRequired: "This methodology suggestion requires your review before approval.",
    confirmSuggestion: "Confirm suggestion for",
    pendingTitle: "Review before approval",
    pendingSingular: "variable still needs your confirmation.",
    pendingPlural: "variables still need your confirmation.",
    proposedClassification: "Proposed classification",
    resolveConflict: "Resolve the document and data conflict in the review card above.",
    conflict: "Conflict for",
    conflictTitle: "Document and data disagree",
    dataSays: "Data classification",
    documentSays: "Document classification",
    evidence: "Document evidence",
    analysisChange: "This choice changes the analysis.",
    useDocument: "Use document classification for",
    useData: "Use data classification for",
    methods: "Planned methods",
    blocked: "This choice blocks analysis",
    observations: "observations",
    missing: "missing", unique: "unique", role: "Role for", kind: "Kind for", variables: "Variable structure", warnings: "Questions to resolve",
    roles: { none: "None", outcome: "Outcome", exposure: "Exposure", covariate: "Covariate", pair_id: "Pair ID", exclude: "Exclude" },
    kinds: { continuous: "Continuous", binary: "Binary", categorical: "Categorical", date: "Date", identifier: "Identifier", exclude: "Exclude" },
  },
  tr: {
    eyebrow: "02 / Veri kökeni",
    title: "Veri ve değişkenler",
    intro: "Değiştirilemez bir Excel çalışma kitabı içe aktarın; planlamadan önce değişken rollerini ve kodlamayı inceleyin.",
    import: "Excel içe aktar",
    importing: "Excel içe aktarılıyor…",
    noFile: "Çalışma kitabı seçilmedi",
    selected: "Seçilen çalışma kitabı",
    approve: "Veri yapısını onayla",
    approved: "Veri yapısı onaylandı",
    approving: "Veri yapısı onaylanıyor…",
    approvalFailure: "Veri yapısı onayı tamamlanamadı. Çalışma kitabını gözden geçirip yeniden deneyin.",
    privacy: "Burada yalnızca dosya adı gösterilir. Orijinal çalışma kitabının üzerine yazılmaz.",
    pickerFailure: "Çalışma kitabı seçici açılamadı. Lütfen yeniden deneyin.",
    profileFailure: "Excel dosyası okunamadı. Geçerli bir XLSX dosyası olduğunu denetleyip yeniden deneyin.",
    briefFailure: "Excel'i içe aktarmadan önce çalışma özetindeki zorunlu alanları tamamlayın.",
    matchingFailure: "Excel okundu; ancak proje ve değişken önerileri hazırlanamadı. Çalışma özetini gözden geçirip yeniden deneyin.",
    profilingStatus: "Excel yapısı bu Mac üzerinde okunuyor…",
    projectStatus: "Excel hazır. Açılan pencerede yerel BioStat projesinin kaydedileceği yeri seçin; ardından yerel yapay zekâ metodolojiyi değişkenlerle eşleştirecek.",
    acceptRemaining: "Kalan uygun değişkenleri kabul et",
    reviewRequired: "Bu metodoloji önerisi onaydan önce incelemenizi gerektiriyor.",
    confirmSuggestion: "Öneriyi onayla",
    pendingTitle: "Onaydan önce inceleyin",
    pendingSingular: "değişken hâlâ onayınızı bekliyor.",
    pendingPlural: "değişken hâlâ onayınızı bekliyor.",
    proposedClassification: "Önerilen sınıflandırma",
    resolveConflict: "Yukarıdaki inceleme kartında doküman ve veri çelişkisini çözün.",
    conflict: "Çelişki",
    conflictTitle: "Doküman ve veri uyuşmuyor",
    dataSays: "Veri sınıflandırması",
    documentSays: "Doküman sınıflandırması",
    evidence: "Doküman kanıtı",
    analysisChange: "Bu seçim analizi değiştirir.",
    useDocument: "Doküman sınıflandırmasını kullan",
    useData: "Veri sınıflandırmasını kullan",
    methods: "Planlanan yöntemler",
    blocked: "Bu seçim analizi engelliyor",
    observations: "gözlem",
    missing: "eksik", unique: "benzersiz", role: "Rol", kind: "Tür", variables: "Değişken yapısı", warnings: "Çözülmesi gereken sorular",
    roles: { none: "Yok", outcome: "Sonuç", exposure: "Maruziyet", covariate: "Kovaryat", pair_id: "Eşleştirme kimliği", exclude: "Dışla" },
    kinds: { continuous: "Sürekli", binary: "İkili", categorical: "Kategorik", date: "Tarih", identifier: "Tanımlayıcı", exclude: "Dışla" },
  },
} as const;

function basename(path: string): string {
  return path.split(/[\\/]/).at(-1) ?? path;
}

// This threshold is intentionally aligned with the uncalibrated matcher threshold.
// Plan 3's gold set must calibrate both values together.
const LOW_CONFIDENCE = 0.8;

const EMPTY_PROPOSALS: VariableProposalResponse = { proposals: [], conflicts: [] };

function waitForPaint(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => resolve());
    else setTimeout(resolve, 0);
  });
}

function rolesForProfile(
  profile: DataProfile,
  brief: StudyBrief | undefined,
  proposals: VariableProposalResponse,
): Record<string, VariableRole> {
  return Object.fromEntries(Object.entries(profile.variables).map(([name, variable]) => {
    let role = "none";
    if (brief?.outcome_variables.includes(name)) role = "outcome";
    else if (brief?.exposure_variables?.includes(name)) role = "exposure";
    else if (brief?.covariates?.includes(name)) role = "covariate";
    else if (brief?.pair_id_variable === name) role = "pair_id";
    const inferred = variable.kind === "identifier-candidate" ? "identifier" : variable.kind;
    const kind = ["continuous", "binary", "categorical", "date", "identifier"].includes(inferred) ? inferred : "exclude";
    const proposal = proposals.proposals.find((item) => item.column === name);
    const proposedRole = proposal?.role?.value;
    const proposedKind = proposal?.kind?.value;
    return [name, {
      name,
      role: proposedRole && proposedRole in labels.en.roles ? proposedRole : role,
      kind: proposedKind && proposedKind in labels.en.kinds ? proposedKind : kind,
      confirmed: false,
    }];
  }));
}

function proposalConfidence(proposal: RoleProposalDto | undefined): number {
  return Math.min(proposal?.role?.confidence ?? 1, proposal?.kind?.confidence ?? 1);
}

function ConflictChoice({
  conflict,
  displayName,
  language,
  onChoose,
}: {
  conflict: ConflictDto;
  displayName: string;
  language: "en" | "tr";
  onChoose(kind: string): void;
}) {
  const copy = labels[language];
  const choices = [
    {
      key: "document",
      title: copy.documentSays,
      kind: conflict.document_kind,
      methods: conflict.methods_if_document,
      blocked: conflict.blocked_if_document,
      action: `${copy.useDocument} ${displayName}`,
    },
    {
      key: "data",
      title: copy.dataSays,
      kind: conflict.data_kind,
      methods: conflict.methods_if_data,
      blocked: conflict.blocked_if_data,
      action: `${copy.useData} ${displayName}`,
    },
  ];

  return (
    <article className="plan-item conflict-card" role="group" aria-label={`${copy.conflict} ${displayName}`}>
      <div className="plan-kicker">{copy.conflictTitle}</div>
      <h3>{copy.conflict} {displayName}</h3>
      {conflict.evidence ? <p className="form-help evidence-quote"><strong>{copy.evidence}:</strong> {conflict.evidence}</p> : null}
      <p className="warning-line"><span aria-hidden="true">!</span>{copy.analysisChange}</p>
      <div className="plan-detail-grid">
        {choices.map((choice) => <section key={choice.key}>
          <h4>{choice.title}: {labels[language].kinds[choice.kind as keyof typeof labels[typeof language]["kinds"]] ?? choice.kind}</h4>
          {choice.methods.length ? <p><strong>{copy.methods}:</strong> {choice.methods.map((method) => methodLabel(method, language)).join(", ")}</p> : null}
          {choice.blocked.length ? <p className="warning-line"><strong>{copy.blocked}:</strong> {choice.blocked.join(", ")}</p> : null}
          <button type="button" className="secondary-action" aria-label={choice.action} onClick={() => onChoose(choice.kind)}>{choice.action}</button>
        </section>)}
      </div>
    </article>
  );
}

export function DataIntake({ api, dataFile, approved, language, brief, methodology, onFile, onApproval }: DataIntakeProps) {
  const copy = labels[language];
  const [importFailure, setImportFailure] = useState<"picker" | "profile" | "brief" | "matching" | null>(null);
  const [profile, setProfile] = useState<DataProfile | null>(null);
  const [roles, setRoles] = useState<Record<string, VariableRole>>({});
  const [approving, setApproving] = useState(false);
  const [approvalFailed, setApprovalFailed] = useState(false);
  const [proposalData, setProposalData] = useState<VariableProposalResponse>(EMPTY_PROPOSALS);
  const [importStage, setImportStage] = useState<"profiling" | "project" | null>(null);
  const [importing, setImporting] = useState(false);
  const [preparationReady, setPreparationReady] = useState(false);

  useEffect(() => {
    if (dataFile !== null) return;
    setImportFailure(null);
    setProfile(null);
    setRoles({});
    setApprovalFailed(false);
    setProposalData(EMPTY_PROPOSALS);
    setImportStage(null);
    setImporting(false);
    setPreparationReady(false);
  }, [dataFile]);

  const chooseFile = async () => {
    if (importing) return;
    setImporting(true);
    let path: string | null;
    try {
      path = await api.selectDataFile();
    } catch {
      setImportFailure("picker");
      setImporting(false);
      return;
    }
    if (!path) {
      setImporting(false);
      return;
    }
    setImportFailure(null);
    onFile(path);
    setProfile(null);
    setRoles({});
    setProposalData(EMPTY_PROPOSALS);
    setPreparationReady(false);
    setImportStage("profiling");
    let nextProfile: DataProfile;
    try {
      if (!api.profileData) throw new Error("profile_unavailable");
      nextProfile = await api.profileData();
    } catch {
      setImportFailure("profile");
      setImportStage(null);
      setImporting(false);
      return;
    }
    setProfile(nextProfile);
    setRoles(rolesForProfile(nextProfile, brief, EMPTY_PROPOSALS));
    let nextProposals = EMPTY_PROPOSALS;
    if (brief && api.prepareDataStructure) {
      try {
        setImportStage("project");
        // Paint the parsed workbook and guidance before Electron opens the
        // native project-save dialog over the application window.
        await waitForPaint();
        nextProposals = await api.prepareDataStructure({ ...brief, language }, methodology ?? null);
      } catch (error) {
        setImportFailure(error instanceof AnalysisApiError && error.code === "validation_error" ? "brief" : "matching");
        setImportStage(null);
        setImporting(false);
        return;
      }
    }
    setProposalData(nextProposals);
    setRoles(rolesForProfile(nextProfile, brief, nextProposals));
    setPreparationReady(true);
    setImportStage(null);
    setImporting(false);
  };
  const acceptRemaining = () => {
    const conflicts = new Set(proposalData.conflicts.map((conflict) => conflict.column));
    const proposals = new Map(proposalData.proposals.map((proposal) => [proposal.column, proposal]));
    setRoles((current) => Object.fromEntries(Object.entries(current).map(([name, role]) => [
      name,
      !conflicts.has(name) && proposalConfidence(proposals.get(name)) >= LOW_CONFIDENCE
        ? { ...role, confirmed: true }
        : role,
    ])));
  };
  const approve = async () => {
    setApproving(true);
    setApprovalFailed(false);
    try {
      await onApproval(Object.values(roles));
    } catch {
      setApprovalFailed(true);
    } finally {
      setApproving(false);
    }
  };
  const conflictColumns = new Set(proposalData.conflicts.map((conflict) => conflict.column));
  const proposalsByColumn = new Map(proposalData.proposals.map((proposal) => [proposal.column, proposal]));
  const hasBulkAcceptableRole = Object.entries(roles).some(([name, role]) => (
    !role.confirmed
    && !conflictColumns.has(name)
    && proposalConfidence(proposalsByColumn.get(name)) >= LOW_CONFIDENCE
  ));
  const pendingReview = Object.entries(roles).filter(([name, role]) => (
    !role.confirmed
    && (conflictColumns.has(name) || proposalConfidence(proposalsByColumn.get(name)) < LOW_CONFIDENCE)
  ));

  return (
    <section className="task-card" aria-labelledby="data-title" aria-busy={importing}>
      <header className="task-heading">
        <p className="eyebrow">{copy.eyebrow}</p>
        <h1 id="data-title">{copy.title}</h1>
        <p className="lede">{copy.intro}</p>
      </header>
      <div className="drop-panel">
        <div className="workbook-glyph" aria-hidden="true">XLSX</div>
        <div>
          <p className="drop-title">{dataFile ? copy.selected : copy.noFile}</p>
          {dataFile && <p className="file-name">{basename(dataFile)}</p>}
          {profile !== null ? <p className="form-help">{profile.rows} {copy.observations}</p> : null}
          <p className="form-help">{copy.privacy}</p>
        </div>
        <button type="button" className="primary-action" disabled={importing} onClick={chooseFile}>{importing ? copy.importing : copy.import}</button>
      </div>
      {importStage ? <p className="import-status" role="status" aria-live="polite">{importStage === "profiling" ? copy.profilingStatus : copy.projectStatus}</p> : null}
      {profile ? <section className="variable-profile" aria-labelledby="variable-profile-title">
        <h2 id="variable-profile-title">{copy.variables}</h2>
        {preparationReady && hasBulkAcceptableRole ? <button type="button" className="secondary-action" onClick={acceptRemaining}>{copy.acceptRemaining}</button> : null}
        {proposalData.conflicts.map((conflict) => <ConflictChoice
          key={conflict.column}
          conflict={conflict}
          displayName={profile.variables[conflict.column]?.display_name ?? conflict.column}
          language={language}
          onChoose={(kind) => setRoles((current) => ({ ...current, [conflict.column]: { ...current[conflict.column], kind, confirmed: true } }))}
        />)}
        {Object.entries(profile.variables).map(([name, variable]) => {
          const proposal = proposalData.proposals.find((item) => item.column === name);
          const evidence = proposal?.role?.evidence ?? proposal?.kind?.evidence;
          return <article key={name} className="variable-row">
            <h3>{variable.display_name}</h3><p>{variable.non_missing} · {variable.missing} {copy.missing} · {variable.unique_values} {copy.unique}</p>
            {evidence ? <p className="form-help evidence-quote"><strong>{copy.evidence}:</strong> {evidence}</p> : null}
            <label>{copy.role} {variable.display_name}<select disabled={!preparationReady} aria-label={`${copy.role} ${variable.display_name}`} value={roles[name]?.role ?? "none"} onChange={(event) => setRoles((current) => ({ ...current, [name]: { ...current[name], role: event.target.value, confirmed: true } }))}>{Object.entries(copy.roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>{copy.kind} {variable.display_name}<select disabled={!preparationReady} aria-label={`${copy.kind} ${variable.display_name}`} value={roles[name]?.kind ?? "exclude"} onChange={(event) => setRoles((current) => ({ ...current, [name]: { ...current[name], kind: event.target.value, confirmed: true } }))}>{Object.entries(copy.kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            {proposal && !roles[name]?.confirmed && proposalConfidence(proposal) < LOW_CONFIDENCE && !conflictColumns.has(name) ? <div className="proposal-confirmation">
              <p className="form-help">{copy.reviewRequired}</p>
              <button type="button" className="secondary-action" aria-label={`${copy.confirmSuggestion} ${variable.display_name}`} onClick={() => setRoles((current) => ({ ...current, [name]: { ...current[name], confirmed: true } }))}>{copy.confirmSuggestion} {variable.display_name}</button>
            </div> : null}
          </article>;
        })}
        {profile.warnings.length ? <div className="warning-line"><strong>{copy.warnings}</strong><ul>{profile.warnings.map((warning) => <li key={`${warning.code}:${warning.column ?? "all"}`}>{warning.message}</li>)}</ul></div> : null}
      </section> : null}
      {profile && preparationReady && !hasBulkAcceptableRole && pendingReview.length > 0 ? <section className="pending-review" aria-labelledby="pending-review-title">
        <h2 id="pending-review-title">{copy.pendingTitle}</h2>
        <p><strong>{pendingReview.length}</strong> {pendingReview.length === 1 ? copy.pendingSingular : copy.pendingPlural}</p>
        <div className="pending-review-list">
          {pendingReview.map(([name, role]) => {
            const variable = profile.variables[name];
            const displayName = variable?.display_name ?? name;
            const proposal = proposalsByColumn.get(name);
            const evidence = proposal?.role?.evidence ?? proposal?.kind?.evidence;
            const roleLabel = copy.roles[role.role as keyof typeof copy.roles] ?? role.role;
            const kindLabel = copy.kinds[role.kind as keyof typeof copy.kinds] ?? role.kind;
            return <article key={name} className="pending-review-item">
              <div>
                <h3>{displayName}</h3>
                <p><strong>{copy.proposedClassification}:</strong> {roleLabel} · {kindLabel}</p>
                {evidence ? <p className="form-help evidence-quote"><strong>{copy.evidence}:</strong> {evidence}</p> : null}
                {conflictColumns.has(name) ? <p className="warning-line">{copy.resolveConflict}</p> : null}
              </div>
              {!conflictColumns.has(name) ? <button type="button" className="primary-action" aria-label={`${copy.confirmSuggestion} ${displayName}`} onClick={() => setRoles((current) => ({ ...current, [name]: { ...current[name], confirmed: true } }))}>{copy.confirmSuggestion} {displayName}</button> : null}
            </article>;
          })}
        </div>
      </section> : null}
      {importFailure ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{importFailure === "picker" ? copy.pickerFailure : importFailure === "profile" ? copy.profileFailure : importFailure === "brief" ? copy.briefFailure : copy.matchingFailure}</p></div> : null}
      {approvalFailed ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{copy.approvalFailure}</p></div> : null}
      <div className="task-footer">
        <p className="microcopy">XLSX</p>
        <button
          type="button"
          className="secondary-action"
          disabled={!profile || !preparationReady || Object.keys(roles).length !== Object.keys(profile.variables).length || Object.values(roles).some((role) => !role.confirmed) || approved || approving}
          onClick={() => void approve()}
        >
          {approved ? copy.approved : approving ? copy.approving : copy.approve}
        </button>
      </div>
    </section>
  );
}
