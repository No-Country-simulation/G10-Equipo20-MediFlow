import React, { useState } from 'react';
import { DocumentMetadata, PatientData, ClinicalVitals } from '../../types';

interface Screen3IntegratedCockpitProps {
  onGoToCriticalAlert: () => void;
  onGoToHumanReview: () => void;
  onGoToDelivered: () => void;
  patient: PatientData;
  document: DocumentMetadata;
  vitals: ClinicalVitals;
}

export const Screen3IntegratedCockpit: React.FC<Screen3IntegratedCockpitProps> = ({
  onGoToCriticalAlert,
  onGoToHumanReview,
  onGoToDelivered,
  patient,
  document: doc,
  vitals
}) => {
  const [sliceIndex, setSliceIndex] = useState(48);
  const [zoom, setZoom] = useState(100);
  const [contrastWindow, setContrastWindow] = useState<'angio' | 'lung' | 'bone'>('angio');
  const [showCrosshairs, setShowCrosshairs] = useState(true);

  return (
    <div className="flex-1 p-4 lg:p-6 max-w-[1720px] mx-auto w-full flex flex-col gap-4">
      {/* Top Critical Alert Banner with Live Plazo */}
      <section className="bg-[#D94545] text-white rounded-lg p-3.5 sm:p-4 shadow-md flex flex-col sm:flex-row items-center justify-between gap-3 animate-pulse-subtle">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-2xl text-white animate-bounce">
              emergency_home
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-extrabold text-sm sm:text-base tracking-wide uppercase">
                🚨 ALERTA CRÍTICA: Tromboembolismo Pulmonar (TEP)
              </span>
              <span className="bg-white text-[#D94545] px-2 py-0.5 rounded font-mono font-bold text-xs shadow-xs">
                NEWS2: {vitals.news2Score} pts
              </span>
            </div>
            <p className="text-xs text-white/90 mt-0.5 font-medium">
              Plazo de intervención inmediata &lt; 60 min (Tiempo Restante estimado: <strong>00:48:15</strong>) • Prioridad C1 Resus
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
          <button
            onClick={onGoToCriticalAlert}
            className="px-4 py-2 bg-white text-[#D94545] hover:bg-red-50 rounded-lg text-xs font-bold transition-all shadow-md flex items-center gap-1.5 cursor-pointer"
          >
            <span>Ver Protocolo de Emergencia Crítica</span>
            <span className="material-symbols-outlined text-sm">open_in_new</span>
          </button>
        </div>
      </section>

      {/* Main Grid: Left Slice Viewer + Transcription, Right Structured Data & Validation */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 items-start">
        {/* Left Column (7 cols): Minimalist dropzone + AngioTC slice viewer + Transcription */}
        <section className="lg:col-span-7 flex flex-col gap-4">
          {/* Diagnostic Slice Viewer Card */}
          <div className="bg-white rounded-lg border border-[#1E5A52]/20 shadow-xs overflow-hidden flex flex-col">
            <div className="px-4 py-3 bg-[#F6FAF8] border-b border-[#1E5A52]/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#1E5A52] text-lg">radiology</span>
                <h2 className="text-xs font-bold text-[#1A2F2B] uppercase tracking-wider">
                  Tomografía Computarizada de Tórax (AngioTC)
                </h2>
              </div>
              <div className="flex items-center gap-2 text-xs font-mono">
                <span className="text-slate-500">Corte:</span>
                <span className="bg-white px-2 py-0.5 rounded border border-slate-200 font-bold text-[#1E5A52]">
                  #{sliceIndex} / 96
                </span>
              </div>
            </div>

            {/* CT Axial Slice Interactive Canvas */}
            <div className="p-4 bg-slate-950 flex flex-col items-center justify-center relative select-none min-h-[380px]">
              {/* CT Slice View Simulation using SVG Vector Graphics */}
              <div className="relative w-full max-w-[440px] aspect-square flex items-center justify-center">
                <svg viewBox="0 0 400 400" className="w-full h-full">
                  {/* Body outline ellipse */}
                  <ellipse cx="200" cy="200" rx="175" ry="155" fill="#14191d" stroke="#2c3b47" strokeWidth="2" />
                  
                  {/* Thorax wall & subcutaneous fat */}
                  <ellipse cx="200" cy="200" rx="165" ry="145" fill="#1c2630" stroke="#485c6e" strokeWidth="3" />
                  
                  {/* Spine vertebra */}
                  <path d="M185,320 L215,320 L220,345 L180,345 Z" fill="#b0bec5" stroke="#eceff1" strokeWidth="1.5" />
                  <ellipse cx="200" cy="315" rx="14" ry="10" fill="#cfd8dc" />

                  {/* Left & Right Lung fields (dark parenchymal areas) */}
                  <path d="M85,150 Q110,120 155,140 Q150,230 110,265 Q75,230 85,150 Z" fill="#0b1013" stroke="#22303c" strokeWidth="2" />
                  <path d="M315,150 Q290,120 245,140 Q250,230 290,265 Q325,230 315,150 Z" fill="#0b1013" stroke="#22303c" strokeWidth="2" />

                  {/* Mediastinum & Cardiac silhouette with contrast */}
                  <path d="M160,150 Q200,130 240,150 Q250,250 200,270 Q150,250 160,150 Z" fill="#2a3844" />
                  
                  {/* Ascending and Descending Aorta */}
                  <circle cx="185" cy="180" r="16" fill="#cfd8dc" stroke="#ffffff" strokeWidth="1.5" />
                  <circle cx="215" cy="245" r="14" fill="#90a4ae" stroke="#cfd8dc" strokeWidth="1" />

                  {/* Main Pulmonary Artery & Right Pulmonary Branch */}
                  <path d="M185,160 Q215,155 220,185 Q190,195 185,160 Z" fill="#e0e0e0" />
                  <path d="M220,180 Q255,190 265,215 Q245,225 215,200 Z" fill="#b0bec5" />

                  {/* TEP THROMBUS DEFECT - Dark filling defect inside right pulmonary artery */}
                  <g className="cursor-pointer" onClick={() => alert('Defecto de llene identificado: Trombo oclusivo en arteria pulmonar principal derecha (SLA Inmediato).')}>
                    <ellipse cx="238" cy="198" rx="11" ry="7" fill="#1c242b" stroke="#D94545" strokeWidth="2" className="animate-pulse" />
                    
                    {/* Red Target Reticle */}
                    <circle cx="238" cy="198" r="22" fill="none" stroke="#D94545" strokeWidth="1.5" strokeDasharray="4 2" />
                    <line x1="238" y1="170" x2="238" y2="226" stroke="#D94545" strokeWidth="1" strokeDasharray="2 2" />
                    <line x1="210" y1="198" x2="266" y2="198" stroke="#D94545" strokeWidth="1" strokeDasharray="2 2" />
                  </g>

                  {/* Label pointers */}
                  <text x="50" y="50" fill="#8ED1A4" fontSize="11" fontFamily="monospace">R (Derecha)</text>
                  <text x="315" y="50" fill="#8ED1A4" fontSize="11" fontFamily="monospace">L (Izquierda)</text>
                  <text x="180" y="380" fill="#78909c" fontSize="10" fontFamily="monospace">POSTERIOR</text>
                  <text x="180" y="25" fill="#78909c" fontSize="10" fontFamily="monospace">ANTERIOR</text>

                  {/* Telemetry OSD text */}
                  <text x="15" y="365" fill="#8ED1A4" fontSize="10" fontFamily="monospace">WL: 40 WW: 400 (Angio)</text>
                  <text x="15" y="380" fill="#8ED1A4" fontSize="10" fontFamily="monospace">FOV: 340mm | 120kV</text>
                </svg>

                {/* Target badge overlay */}
                <div className="absolute top-4 right-4 bg-red-950/80 border border-red-500/80 text-red-300 px-2.5 py-1 rounded text-[11px] font-mono shadow-md backdrop-blur-xs">
                  <span className="font-bold text-red-400">DEFECTO DE LLENE TEP</span>
                  <p className="text-[10px] text-white/80">Art. Pulmonar Derecha (99.1%)</p>
                </div>
              </div>

              {/* Slider & Windowing Bar */}
              <div className="w-full mt-3 pt-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-300 font-mono gap-3 px-2">
                <div className="flex items-center gap-2 flex-1 max-w-xs">
                  <span className="text-[10px] text-slate-400">CORTE AXIAL:</span>
                  <input
                    type="range"
                    min="1"
                    max="96"
                    value={sliceIndex}
                    onChange={(e) => setSliceIndex(Number(e.target.value))}
                    className="w-full accent-[#8ED1A4] cursor-pointer"
                  />
                  <span className="w-8 text-right font-bold text-[#8ED1A4]">{sliceIndex}</span>
                </div>

                {/* Preset windows */}
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setContrastWindow('angio')}
                    className={`px-2 py-0.5 rounded text-[10px] ${
                      contrastWindow === 'angio' ? 'bg-[#1E5A52] text-white font-bold' : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    Angio
                  </button>
                  <button
                    onClick={() => setContrastWindow('lung')}
                    className={`px-2 py-0.5 rounded text-[10px] ${
                      contrastWindow === 'lung' ? 'bg-[#1E5A52] text-white font-bold' : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    Pulmón
                  </button>
                  <button
                    onClick={() => setContrastWindow('bone')}
                    className={`px-2 py-0.5 rounded text-[10px] ${
                      contrastWindow === 'bone' ? 'bg-[#1E5A52] text-white font-bold' : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    Óseo
                  </button>
                </div>
              </div>
            </div>

            {/* Radiological Transcription with Highlighted Ambiguity */}
            <div className="p-4 bg-white space-y-2 border-t border-slate-200">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px] text-[#1E5A52]">clinical_notes</span>
                Transcripción Radiológica y Hallazgos Principales
              </span>
              <div className="text-xs text-slate-700 leading-relaxed space-y-1.5 bg-[#F6FAF8] p-3 rounded-lg border border-slate-200 font-sans">
                <p>
                  <strong>Técnica:</strong> Angiotomografía computarizada de arterias pulmonares con bolo de 70 ml de medio de contraste iodado endovenoso en fase arterial precoz.
                </p>
                <p>
                  <strong>Hallazgos Parenquimatosos:</strong> Se constata <mark className="bg-amber-100 text-amber-900 px-1 py-0.5 rounded border border-amber-300 font-semibold">defecto de llene endoluminal extenso en arteria pulmonar principal derecha</mark>, con compromiso de ramas lobares superiores e inferiores. Relación ventrículo derecho/izquierdo de 1.15 indicando tensión miocárdica aguda.
                </p>
                <p className="text-[11px] text-slate-500 italic">
                  <strong>Conclusión:</strong> Tromboembolismo Pulmonar Masivo Agudo con sobrecarga ventricular derecha. Se sugiere correlación clínica urgente y monitoreo hemodinámico estrecho.
                </p>
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 font-mono">
                <span>Ley 19.628: Datos disociados y anonimizados</span>
                <span className="text-[#296a45] font-semibold flex items-center gap-1">
                  <span className="material-symbols-outlined text-[13px]">check_circle</span>
                  Validado por IA Nivel 1 (140ms)
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Right Column (5 cols): Structured Clinical Data & Action Center */}
        <section className="lg:col-span-5 flex flex-col gap-4">
          {/* Structured Clinical Data Grid */}
          <div className="bg-white rounded-lg border border-[#1E5A52]/20 shadow-xs p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
              <h3 className="font-bold text-sm text-[#1A2F2B] flex items-center gap-2">
                <span className="material-symbols-outlined text-[#1E5A52] text-lg">schema</span>
                Datos Estructurados del Documento
              </h3>
              <span className="px-2 py-0.5 rounded-full bg-[#adf2c3]/40 text-[#296a45] text-xs font-bold font-mono">
                95% Confianza
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between items-center p-2 rounded bg-[#F6FAF8] border border-slate-200">
                <span className="text-slate-500 font-semibold">Tipo Documento:</span>
                <span className="font-bold text-[#1A2F2B]">Informe AngioTC (24627-2)</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-[#F6FAF8] border border-slate-200">
                <span className="text-slate-500 font-semibold">Especialidad Receptora:</span>
                <span className="font-bold text-[#1E5A52]">Urgencias Cardiorrespiratorias</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-[#F6FAF8] border border-slate-200">
                <span className="text-slate-500 font-semibold">Destino Asignado:</span>
                <span className="font-mono font-bold text-red-700">Box Reanimación 01</span>
              </div>
            </div>

            {/* Vital signs quick quartet */}
            <div className="pt-2">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-2">
                Signos Vitales Extraídos (NEWS2: 8 Puntos)
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs font-mono">
                <div className="p-2 rounded bg-red-50 border border-red-200">
                  <span className="text-[10px] text-slate-500 block">FC</span>
                  <strong className="text-red-700 text-sm">{vitals.heartRate} lpm</strong>
                  <span className="text-[9px] text-red-600 block">Taquicardia</span>
                </div>
                <div className="p-2 rounded bg-red-50 border border-red-200">
                  <span className="text-[10px] text-slate-500 block">Sat O2</span>
                  <strong className="text-red-700 text-sm">{vitals.spO2}%</strong>
                  <span className="text-[9px] text-red-600 block">Hipoxemia</span>
                </div>
                <div className="p-2 rounded bg-amber-50 border border-amber-200">
                  <span className="text-[10px] text-slate-500 block">PA</span>
                  <strong className="text-amber-800 text-sm">{vitals.bloodPressureSystolic}/{vitals.bloodPressureDiastolic}</strong>
                  <span className="text-[9px] text-amber-700 block">Límite</span>
                </div>
                <div className="p-2 rounded bg-red-50 border border-red-200">
                  <span className="text-[10px] text-slate-500 block">FR</span>
                  <strong className="text-red-700 text-sm">{vitals.respiratoryRate} rpm</strong>
                  <span className="text-[9px] text-red-600 block">Taquipnea</span>
                </div>
              </div>
            </div>
          </div>

          {/* Validation & Human Review Panel */}
          <div className="bg-white rounded-lg border-2 border-[#E8A238]/60 shadow-xs p-5 space-y-3.5">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[#E8A238] text-xl">rate_review</span>
              <h3 className="font-bold text-sm text-[#1A2F2B]">
                Panel de Validación y Revisión Humana Requerida
              </h3>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              El documento presenta alerta crítica por TEP y discrepancia posológica en prescripción asociada (Apixabán 5? mg). Se recomienda verificación visual antes del despacho farmacéutico final.
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-2.5 pt-2">
              <button
                onClick={onGoToHumanReview}
                className="w-full sm:flex-1 py-2.5 px-4 rounded-lg bg-[#E8A238] hover:bg-[#d9942a] text-[#1A2F2B] font-bold text-xs flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
              >
                <span className="material-symbols-outlined text-base">zoom_in</span>
                <span>Corregir en Estación de Revisión (4/5)</span>
              </button>
              <button
                onClick={onGoToDelivered}
                className="w-full sm:flex-1 py-2.5 px-4 rounded-lg bg-[#1E5A52] hover:bg-[#16443E] text-white font-bold text-xs flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
              >
                <span className="material-symbols-outlined text-base">task_alt</span>
                <span>Aprobar y Enrutar a Urgencias</span>
              </button>
            </div>
          </div>

          {/* Delivery Target Confirmation Pill Card */}
          <div className="p-3.5 rounded-lg bg-[#adf2c3]/20 border border-[#8ED1A4] flex items-center justify-between text-xs">
            <div className="flex items-center gap-2.5">
              <span className="material-symbols-outlined text-[#296a45] text-lg">local_shipping</span>
              <div>
                <span className="font-bold text-[#1A2F2B] block">Entregado a: Cola_Emergencia_Medica</span>
                <span className="text-slate-600 text-[11px]">Enrutamiento directo y seguro a Box de Reanimación</span>
              </div>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#296a45] text-white font-mono">
              SYNC
            </span>
          </div>

          {/* Clinical protocol quick recommendations */}
          <div className="p-3.5 rounded-lg bg-[#F6FAF8] border border-slate-200 text-xs space-y-1">
            <span className="font-bold text-[#1E5A52] flex items-center gap-1">
              <span className="material-symbols-outlined text-sm">clinical_notes</span>
              Protocolo Sugerido de Rescate:
            </span>
            <ul className="list-disc pl-4 text-slate-600 space-y-0.5 text-[11px]">
              <li>Oxigenoterapia alto flujo inmediata (meta SpO2 &gt; 92%).</li>
              <li>Acceso venoso periférico 16G bilateral + monitorización invasiva.</li>
              <li>Evaluación por cardiólogo intervencionista / trombolisis sistémica.</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
};
