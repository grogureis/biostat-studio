import type { AnalysisApi } from "../../api/client";
import type { DataProfile, StudyBrief, VariableRole } from "../../api/types";
import { useState } from "react";

interface DataIntakeProps {
  api: AnalysisApi;
  dataFile: string | null;
  approved: boolean;
  language: "en" | "tr";
  brief?: StudyBrief;
  onFile(path: string | null): void;
  onApproval(roles: VariableRole[]): Promise<void>;
}

const labels = {
  en: {
    eyebrow: "02 / Data provenance",
    title: "Data & variables",
    intro: "Import an immutable Excel workbook, then review variable roles and coding before planning.",
    import: "Import Excel",
    noFile: "No workbook selected",
    selected: "Selected workbook",
    approve: "Approve data structure",
    approved: "Data structure approved",
    approving: "Approving data structure…",
    approvalFailure: "Data structure approval could not be completed. Review the workbook and try again.",
    privacy: "Only the file name is shown here. The original workbook is never overwritten.",
  pickerFailure: "The workbook picker could not be opened. Try again.",
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
    noFile: "Çalışma kitabı seçilmedi",
    selected: "Seçilen çalışma kitabı",
    approve: "Veri yapısını onayla",
    approved: "Veri yapısı onaylandı",
    approving: "Veri yapısı onaylanıyor…",
    approvalFailure: "Veri yapısı onayı tamamlanamadı. Çalışma kitabını gözden geçirip yeniden deneyin.",
    privacy: "Burada yalnızca dosya adı gösterilir. Orijinal çalışma kitabının üzerine yazılmaz.",
  pickerFailure: "Çalışma kitabı seçici açılamadı. Lütfen yeniden deneyin.",
    observations: "gözlem",
    missing: "eksik", unique: "benzersiz", role: "Rol", kind: "Tür", variables: "Değişken yapısı", warnings: "Çözülmesi gereken sorular",
    roles: { none: "Yok", outcome: "Sonuç", exposure: "Maruziyet", covariate: "Kovaryat", pair_id: "Eşleştirme kimliği", exclude: "Dışla" },
    kinds: { continuous: "Sürekli", binary: "İkili", categorical: "Kategorik", date: "Tarih", identifier: "Tanımlayıcı", exclude: "Dışla" },
  },
} as const;

function basename(path: string): string {
  return path.split(/[\\/]/).at(-1) ?? path;
}

export function DataIntake({ api, dataFile, approved, language, brief, onFile, onApproval }: DataIntakeProps) {
  const copy = labels[language];
  const [pickerFailed, setPickerFailed] = useState(false);
  const [profile, setProfile] = useState<DataProfile | null>(null);
  const [roles, setRoles] = useState<Record<string, VariableRole>>({});
  const [approving, setApproving] = useState(false);
  const [approvalFailed, setApprovalFailed] = useState(false);
  const chooseFile = async () => {
    try {
      const path = await api.selectDataFile();
      setPickerFailed(false);
      onFile(path);
      const nextProfile = path && api.profileData ? await api.profileData() : null;
      setProfile(nextProfile);
      if (nextProfile) {
        setRoles(Object.fromEntries(Object.entries(nextProfile.variables).map(([name, variable]) => {
          let role = "none";
          if (brief?.outcome_variables.includes(name)) role = "outcome";
          else if (brief?.exposure_variables?.includes(name)) role = "exposure";
          else if (brief?.covariates?.includes(name)) role = "covariate";
          else if (brief?.pair_id_variable === name) role = "pair_id";
          const inferred = variable.kind === "identifier-candidate" ? "identifier" : variable.kind;
          const kind = ["continuous", "binary", "categorical", "date", "identifier"].includes(inferred) ? inferred : "exclude";
          return [name, { name, role, kind, confirmed: true }];
        })));
      }
    } catch {
      setPickerFailed(true);
    }
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

  return (
    <section className="task-card" aria-labelledby="data-title">
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
        <button type="button" className="primary-action" onClick={chooseFile}>{copy.import}</button>
      </div>
      {profile ? <section className="variable-profile" aria-labelledby="variable-profile-title">
        <h2 id="variable-profile-title">{copy.variables}</h2>
        {Object.entries(profile.variables).map(([name, variable]) => <article key={name} className="variable-row">
          <h3>{variable.display_name}</h3><p>{variable.non_missing} · {variable.missing} {copy.missing} · {variable.unique_values} {copy.unique}</p>
          <label>{copy.role} {variable.display_name}<select aria-label={`${copy.role} ${variable.display_name}`} value={roles[name]?.role ?? "none"} onChange={(event) => setRoles((current) => ({ ...current, [name]: { ...current[name], role: event.target.value, confirmed: true } }))}>{Object.entries(copy.roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>{copy.kind} {variable.display_name}<select aria-label={`${copy.kind} ${variable.display_name}`} value={roles[name]?.kind ?? "exclude"} onChange={(event) => setRoles((current) => ({ ...current, [name]: { ...current[name], kind: event.target.value, confirmed: true } }))}>{Object.entries(copy.kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </article>)}
        {profile.warnings.length ? <div className="warning-line"><strong>{copy.warnings}</strong><ul>{profile.warnings.map((warning) => <li key={`${warning.code}:${warning.column ?? "all"}`}>{warning.message}</li>)}</ul></div> : null}
      </section> : null}
      {pickerFailed ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{copy.pickerFailure}</p></div> : null}
      {approvalFailed ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{copy.approvalFailure}</p></div> : null}
      <div className="task-footer">
        <p className="microcopy">XLSX</p>
        <button
          type="button"
          className="secondary-action"
          disabled={!profile || Object.keys(roles).length !== Object.keys(profile.variables).length || approved || approving}
          onClick={() => void approve()}
        >
          {approved ? copy.approved : approving ? copy.approving : copy.approve}
        </button>
      </div>
    </section>
  );
}
