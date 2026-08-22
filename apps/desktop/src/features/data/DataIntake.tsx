import type { AnalysisApi } from "../../api/client";
import { useState } from "react";

interface DataIntakeProps {
  api: AnalysisApi;
  dataFile: string | null;
  approved: boolean;
  language: "en" | "tr";
  onFile(path: string | null): void;
  onApproval(): Promise<void>;
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
  },
} as const;

function basename(path: string): string {
  return path.split(/[\\/]/).at(-1) ?? path;
}

export function DataIntake({ api, dataFile, approved, language, onFile, onApproval }: DataIntakeProps) {
  const copy = labels[language];
  const [pickerFailed, setPickerFailed] = useState(false);
  const [rows, setRows] = useState<number | null>(null);
  const [approving, setApproving] = useState(false);
  const [approvalFailed, setApprovalFailed] = useState(false);
  const chooseFile = async () => {
    try {
      const path = await api.selectDataFile();
      setPickerFailed(false);
      onFile(path);
      setRows(path && api.profileData ? (await api.profileData()).rows : null);
    } catch {
      setPickerFailed(true);
    }
  };
  const approve = async () => {
    setApproving(true);
    setApprovalFailed(false);
    try {
      await onApproval();
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
          {rows !== null ? <p className="form-help">{rows} {copy.observations}</p> : null}
          <p className="form-help">{copy.privacy}</p>
        </div>
        <button type="button" className="primary-action" onClick={chooseFile}>{copy.import}</button>
      </div>
      {pickerFailed ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{copy.pickerFailure}</p></div> : null}
      {approvalFailed ? <div className="error-panel" role="alert"><span aria-hidden="true">!</span><p>{copy.approvalFailure}</p></div> : null}
      <div className="task-footer">
        <p className="microcopy">XLSX · XLS · CSV</p>
        <button
          type="button"
          className="secondary-action"
          disabled={!dataFile || approved || approving}
          onClick={() => void approve()}
        >
          {approved ? copy.approved : approving ? copy.approving : copy.approve}
        </button>
      </div>
    </section>
  );
}
