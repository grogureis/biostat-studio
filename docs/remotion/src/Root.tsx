import React from 'react';
import {AbsoluteFill, Composition, Still, interpolate, useCurrentFrame} from 'remotion';

type Props = {language: 'en' | 'tr'};
const c = {paper: '#f7f3eb', panel: '#fffdf8', ink: '#183d35', moss: '#286051', muted: '#5c6c63', line: '#d8d6ca', clay: '#ad5339', pale: '#e8eee6'};
const sans = 'Arial, Helvetica, sans-serif';
const serif = 'Georgia, serif';
const mono = 'monospace';

const Frame: React.FC<React.PropsWithChildren<{label: string}>> = ({label, children}) => (
  <AbsoluteFill style={{background: c.paper, color: c.ink, fontFamily: sans, padding: '60px 72px'}}>
    <style>{'* { box-sizing: border-box; }'}</style>
    <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${c.line}`, paddingBottom: 22, fontSize: 20, letterSpacing: 2}}>
      <span style={{fontWeight: 700}}>BIOSTAT STUDIO</span><span style={{color: c.muted}}>{label}</span>
    </div>
    {children}
  </AbsoluteFill>
);

const Icon = ({kind, size = 42}: {kind: string; size?: number}) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    {kind === 'document' && <><path d="M12 5h17l8 8v30H12z M29 5v9h8"/><path d="M18 22h13 M18 29h13 M18 36h8"/></>}
    {kind === 'data' && <><rect x="6" y="7" width="36" height="34" rx="3"/><path d="M6 18h36 M6 29h36 M18 7v34 M30 7v34"/></>}
    {kind === 'check' && <><rect x="7" y="7" width="34" height="34" rx="8"/><path d="m15 24 6 6 12-13"/></>}
    {kind === 'run' && <><circle cx="24" cy="24" r="18"/><path d="m20 15 13 9-13 9z"/></>}
    {kind === 'chart' && <><path d="M7 7v34h35 M14 31l9-11 7 6 11-15"/><circle cx="23" cy="20" r="2"/></>}
    {kind === 'lock' && <><rect x="10" y="21" width="28" height="22" rx="4"/><path d="M16 21v-8a8 8 0 0 1 16 0v8 M24 30v5"/></>}
  </svg>
);

export const Hero = ({language}: Props) => {
  const tr = language === 'tr';
  return <Frame label="APPLE SILICON · macOS">
    <div style={{display: 'flex', flex: 1, gap: 70, alignItems: 'center'}}>
      <div style={{width: 690}}>
        <div style={{color: c.clay, fontSize: 22, letterSpacing: 3, fontWeight: 700, marginBottom: 28}}>{tr ? 'YEREL ANALİZ. AÇIK ONAY.' : 'LOCAL ANALYSIS. EXPLICIT APPROVAL.'}</div>
        <h1 style={{fontFamily: serif, fontWeight: 400, fontSize: 98, letterSpacing: -4, lineHeight: 1.03, margin: '0 0 30px'}}>BioStat<br/>Studio</h1>
        <p style={{fontSize: 34, lineHeight: 1.45, margin: 0, maxWidth: 660}}>{tr ? 'Araştırma sorusundan düzenlenebilir Word Bulgular bölümüne.' : 'From a research question to an editable Word Results section.'}</p>
        <div style={{display: 'flex', gap: 13, marginTop: 35}}>
          {(tr ? ['Çevrimdışı analiz', 'EN / TR rapor'] : ['Offline analysis', 'EN / TR reports']).map(label => <span key={label} style={{padding: '12px 18px', background: c.pale, fontSize: 22, borderRadius: 6}}>{label}</span>)}
        </div>
      </div>
      <div style={{width: 620, position: 'relative'}}>
        <div style={{border: `1px solid ${c.line}`, borderRadius: 16, padding: 34, background: c.panel, boxShadow: '0 20px 50px #183d3510'}}>
          <div style={{display: 'flex', gap: 18, alignItems: 'center', fontSize: 24, paddingBottom: 25, borderBottom: `1px solid ${c.line}`}}><Icon kind="data"/><span>{tr ? 'Excel + çalışma bilgileri' : 'Excel + study metadata'}</span></div>
          <div style={{padding: '28px 0', display: 'flex', gap: 18, alignItems: 'center', color: c.clay}}><Icon kind="check"/><div><strong style={{fontSize: 29}}>{tr ? 'Araştırmacı onayı' : 'Researcher approval'}</strong><div style={{fontSize: 22, marginTop: 8, color: c.muted}}>{tr ? 'Değişkenler ve plan ayrı incelenir' : 'Variables and plan reviewed separately'}</div></div></div>
          <div style={{background: c.moss, color: c.panel, borderRadius: 9, padding: 28, display: 'flex', alignItems: 'center', gap: 18}}><Icon kind="document"/><div><strong style={{fontSize: 29}}>{tr ? 'Word Bulgular bölümü' : 'Word Results section'}</strong><div style={{fontSize: 22, marginTop: 8}}>{tr ? 'Anlatı · tablolar · şekiller' : 'Narrative · tables · figures'}</div></div></div>
        </div>
        <div style={{display: 'flex', alignItems: 'center', gap: 12, fontSize: 23, marginTop: 24}}><Icon kind="lock" size={28}/>{tr ? 'Araştırma verisi Mac üzerinde kalır' : 'Research data stay on your Mac'}</div>
      </div>
    </div>
    <div style={{borderTop: `1px solid ${c.line}`, paddingTop: 22, display: 'flex', justifyContent: 'space-between', fontSize: 20, color: c.muted}}><span>{tr ? 'Yayın öncesi sürüm · operatör kabulü bekleniyor' : 'Pre-release · operator acceptance pending'}</span><span>{tr ? 'Ürün özeti · ekran görüntüsü değildir' : 'Product overview · not a screenshot'}</span></div>
  </Frame>;
};

const steps = {
  en: [
    ['Study brief', 'Question, design and outcomes', 'document', 'Review local suggestions'],
    ['Data & variables', 'Excel columns and variable roles', 'data', 'Approve data structure'],
    ['Analysis plan', 'Method, assumptions and warnings', 'check', 'Approve the plan'],
    ['Run & diagnose', 'Execute the approved plan', 'run', 'Safe progress and cancellation'],
    ['Results review', 'Estimates, 95% CIs and p values', 'chart', 'Check diagnostics and provenance'],
    ['Word report', 'English or Turkish .docx', 'document', 'Narrative, tables and figures'],
  ],
  tr: [
    ['Çalışma özeti', 'Soru, tasarım ve sonlanımlar', 'document', 'Yerel önerileri incele'],
    ['Veri ve değişkenler', 'Excel sütunları ve değişken rolleri', 'data', 'Veri yapısını onayla'],
    ['Analiz planı', 'Yöntem, varsayımlar ve uyarılar', 'check', 'Analiz planını onayla'],
    ['Çalıştır ve tanıla', 'Onaylanmış planı yürüt', 'run', 'İlerleme ve güvenli iptal'],
    ['Sonuçları incele', 'Tahminler, %95 GA ve p değerleri', 'chart', 'Tanıları ve analiz kökenini incele'],
    ['Word raporu', 'İngilizce veya Türkçe .docx', 'document', 'Anlatı, tablolar ve şekiller'],
  ],
};

export const Workflow = ({language, animated = false}: Props & {animated?: boolean}) => {
  const tr = language === 'tr';
  const frame = useCurrentFrame();
  const active = Math.floor(frame / 90) % 6;
  return <Frame label={tr ? 'ARAŞTIRMACININ İŞ AKIŞI' : 'THE RESEARCHER’S WORKFLOW'}>
    <h1 style={{fontFamily: serif, fontSize: 65, fontWeight: 400, letterSpacing: -2, margin: '32px 0 12px'}}>{tr ? 'Altı adım. İki ayrı onay.' : 'Six stages. Two separate approvals.'}</h1>
    <p style={{fontSize: 25, color: c.muted, margin: '0 0 30px'}}>{tr ? 'Ana analiz akışı soldan sağa, ardından ikinci satırdan devam eder.' : 'Read the analysis path left to right, then continue on the second row.'}</p>
    <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20}}>
      {steps[language].map(([title, subtitle, icon, action], i) => <div key={title} style={{height: 205, padding: 26, borderRadius: 10, background: c.panel, border: `2px solid ${i === 1 || i === 2 ? c.clay : c.line}`, opacity: animated ? interpolate(frame, [i * 90, i * 90 + 18], [.38, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1, boxShadow: animated && active === i ? '0 6px 24px #183d3518' : 'none'}}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18}}><span style={{fontFamily: mono, fontSize: 21, color: c.clay}}>0{i + 1}</span><Icon kind={icon} size={33}/></div>
        <strong style={{fontSize: 30}}>{title}</strong>
        <p style={{fontSize: 21, color: c.muted, margin: '10px 0 16px'}}>{subtitle}</p>
        <div style={{fontSize: 19, color: i === 1 || i === 2 ? c.clay : c.moss, fontWeight: 700}}>{i === 1 || i === 2 ? '✓ ' : ''}{action}</div>
      </div>)}
    </div>
    <div style={{marginTop: 26, padding: '20px 25px', background: c.pale, display: 'flex', alignItems: 'center', gap: 22, borderRadius: 8}}>
      <span style={{fontFamily: mono, color: c.moss, fontSize: 28}}>n / β</span><strong style={{fontSize: 25}}>{tr ? 'Güç ve örneklem hesabı' : 'Power & sample size'}</strong><span style={{fontSize: 22, color: c.muted}}>{tr ? 'Bağımsız araç · içe aktarılmış veri gerekmez' : 'Independent tool · no imported dataset required'}</span>
    </div>
    <div style={{marginTop: 22, color: c.muted, fontSize: 20}}>{tr ? 'Veri, roller, çalışma özeti veya plan değişirse sonraki onaylar ve sonuçlar geçersizleşir.' : 'Changes to data, roles, the study brief or the plan invalidate downstream approvals and results.'}</div>
  </Frame>;
};

export const Report = ({language}: Props) => {
  const tr = language === 'tr';
  return <Frame label={tr ? 'DÜZENLENEBİLİR .docx ÇIKTISI' : 'EDITABLE .docx OUTPUT'}>
    <h1 style={{fontFamily: serif, fontSize: 67, fontWeight: 400, letterSpacing: -2, margin: '32px 0 14px'}}>{tr ? 'Bir sonuç paketi. İki rapor dili.' : 'One result bundle. Two report languages.'}</h1>
    <p style={{fontSize: 26, color: c.muted, margin: '0 0 34px'}}>{tr ? 'Anlatı, tablo ve şekiller aynı tamamlanmış analizden türetilir.' : 'Narrative, tables and figures derive from the same completed analysis.'}</p>
    <div style={{display: 'flex', gap: 52, alignItems: 'center'}}>
      <div style={{width: 560, padding: 38, background: c.panel, border: `1px solid ${c.line}`, boxShadow: '8px 10px 0 #e3e3d9', height: 460}}>
        <div style={{fontFamily: serif, fontSize: 45, paddingBottom: 16, borderBottom: `2px solid ${c.ink}`}}>{tr ? 'Bulgular' : 'Results'}<span style={{float: 'right', color: c.clay, fontFamily: sans, fontSize: 20}}>EN / TR</span></div>
        <div style={{margin: '24px 0', fontSize: 21, color: c.muted, lineHeight: 1.6}}>{tr ? 'Örneklem ve eksik veri özeti. Etki tahminleri, güven aralıkları ve uyarılar.' : 'Sample and missingness summary. Effect estimates, confidence intervals and warnings.'}</div>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', borderTop: `1px solid ${c.ink}`, borderBottom: `1px solid ${c.ink}`, padding: '13px 0', fontSize: 18}}><span>{tr ? 'Tahmin' : 'Estimate'}</span><span>{tr ? '%95 GA' : '95% CI'}</span><span>p</span></div>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', borderBottom: `1px solid ${c.ink}`, padding: '17px 0', fontFamily: mono, color: c.muted, fontSize: 21}}><span>···</span><span>···</span><span>···</span></div>
        <div style={{display: 'flex', gap: 15, alignItems: 'center', marginTop: 27, fontSize: 20, color: c.moss}}><Icon kind="chart" size={34}/>{tr ? 'Desteklenen yöntemlerde şekil' : 'Figure for supported methods'}</div>
      </div>
      <div style={{flex: 1}}>
        {(tr ? [
          ['İstatistiksel anlatı', 'Nedensellik iddiası içermeyen Bulgular metni.'],
          ['Tablolar ve şekiller', 'Tahminler, %95 GA, p değerleri ve etki büyüklükleri.'],
          ['Yeniden üretilebilirlik eki', 'Veri parmak izi, plan revizyonu ve analiz kökeni.'],
          ['İngilizce / Türkçe', 'Aynı sayısal sonuçlardan yeniden üretilen raporlar.'],
        ] : [
          ['Statistical narrative', 'Concise Results text without causal claims.'],
          ['Tables & figures', 'Estimates, 95% CIs, p values and effect sizes.'],
          ['Reproducibility appendix', 'Data fingerprint, plan revision and provenance.'],
          ['English / Turkish', 'Reports regenerated from the same numerical results.'],
        ]).map(([title, detail], i) => <div key={title} style={{display: 'flex', gap: 22, padding: '20px 0', borderBottom: `1px solid ${c.line}`}}><span style={{fontFamily: mono, fontSize: 22, color: c.clay, paddingTop: 4}}>0{i + 1}</span><div><strong style={{fontSize: 29}}>{title}</strong><p style={{fontSize: 22, color: c.muted, margin: '10px 0 0', lineHeight: 1.4}}>{detail}</p></div></div>)}
      </div>
    </div>
    <div style={{marginTop: 38, fontSize: 20, color: c.muted}}>{tr ? 'Şematik gösterim · gerçek analiz sonucu veya rapor ekran görüntüsü değildir. Hasta satırları rapora eklenmez.' : 'Schematic illustration · not actual analysis results or a report screenshot. Patient rows are excluded from reports.'}</div>
  </Frame>;
};

const AnimatedWorkflow = (props: Props) => <Workflow language={props.language} animated/>;

export const Root = () => <>
  <Still id="HeroEN" component={Hero} width={1600} height={900} defaultProps={{language: 'en'}}/>
  <Still id="HeroTR" component={Hero} width={1600} height={900} defaultProps={{language: 'tr'}}/>
  <Still id="WorkflowEN" component={Workflow} width={1600} height={900} defaultProps={{language: 'en'}}/>
  <Still id="WorkflowTR" component={Workflow} width={1600} height={900} defaultProps={{language: 'tr'}}/>
  <Still id="ReportEN" component={Report} width={1600} height={900} defaultProps={{language: 'en'}}/>
  <Still id="ReportTR" component={Report} width={1600} height={900} defaultProps={{language: 'tr'}}/>
  <Composition id="WorkflowMotionEN" component={AnimatedWorkflow} width={1600} height={900} fps={30} durationInFrames={540} defaultProps={{language: 'en'}}/>
  <Composition id="WorkflowMotionTR" component={AnimatedWorkflow} width={1600} height={900} fps={30} durationInFrames={540} defaultProps={{language: 'tr'}}/>
</>;
