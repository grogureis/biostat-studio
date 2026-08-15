import type { AnalysisApi } from "../../api/client";

interface DataIntakeProps {
  api: AnalysisApi;
  dataFile: string | null;
  language: "en" | "tr";
  onFile(path: string | null): void;
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
    privacy: "Only the file name is shown here. The original workbook is never overwritten.",
  },
  tr: {
    eyebrow: "02 / Veri kökeni",
    title: "Veri ve değişkenler",
    intro: "Değiştirilemez bir Excel çalışma kitabı içe aktarın; planlamadan önce değişken rollerini ve kodlamayı inceleyin.",
    import: "Excel içe aktar",
    noFile: "Çalışma kitabı seçilmedi",
    selected: "Seçilen çalışma kitabı",
    approve: "Veri yapısını onayla",
    privacy: "Burada yalnızca dosya adı gösterilir. Orijinal çalışma kitabının üzerine yazılmaz.",
  },
} as const;

function basename(path: string): string {
  return path.split(/[\\/]/).at(-1) ?? path;
}

export function DataIntake({ api, dataFile, language, onFile }: DataIntakeProps) {
  const copy = labels[language];
  const chooseFile = async () => onFile(await api.selectDataFile());

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
          <p className="form-help">{copy.privacy}</p>
        </div>
        <button type="button" className="primary-action" onClick={chooseFile}>{copy.import}</button>
      </div>
      <div className="task-footer">
        <p className="microcopy">XLSX · XLS · CSV</p>
        <button type="button" className="secondary-action" disabled={!dataFile}>{copy.approve}</button>
      </div>
    </section>
  );
}
