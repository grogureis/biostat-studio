interface ReportExportProps {
  language: "en" | "tr";
  exporting: boolean;
  savedPath: string | null;
  onExport(): void;
}

const copy = {
  en: { eyebrow: "06 / Manuscript handoff", title: "Word report", intro: "Create a bilingual, publication-ready Results section with its approved tables, figure, and provenance appendix.", export: "Export Word report", saving: "Preparing Word report…", saved: "Word report saved", safeguards: "The exported report contains no original data file path or patient-level data." },
  tr: { eyebrow: "06 / Makale aktarımı", title: "Word raporu", intro: "Onaylanmış tabloları, şekli ve köken ekini içeren iki dilli, yayına hazır bir Sonuçlar bölümü oluşturun.", export: "Word raporunu dışa aktar", saving: "Word raporu hazırlanıyor…", saved: "Word raporu kaydedildi", safeguards: "Dışa aktarılan rapor, özgün veri dosyası yolu veya hasta düzeyinde veri içermez." },
} as const;

export function ReportExport({ language, exporting, savedPath, onExport }: ReportExportProps) {
  const text = copy[language];
  return <section className="task-card" aria-labelledby="report-title">
    <header className="task-heading"><p className="eyebrow">{text.eyebrow}</p><h1 id="report-title">{text.title}</h1><p className="lede">{text.intro}</p></header>
    <div className="report-preview"><span className="report-glyph" aria-hidden="true">DOCX</span><div><h2>Results section</h2><p>{text.safeguards}</p></div></div>
    <footer className="task-footer"><button type="button" className="primary-action" onClick={onExport} disabled={exporting}>{exporting ? text.saving : text.export}</button>{savedPath ? <p role="status" className="saved-status">{text.saved}</p> : null}</footer>
  </section>;
}
