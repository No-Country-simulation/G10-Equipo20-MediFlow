# MediFlow — Sistema Autónomo de Triaje Clínico

> **Hackathon ONE G10 — Equipo 20**  
> Agente autónomo para triaje, extracción estructurada y enrutamiento inteligente de documentos clínicos con foco cardiorrespiratorio y soporte para 18 países hispanohablantes de Latinoamérica.

---

## 🏥 Acerca de MediFlow

MediFlow resuelve el cuello de botella crítico en la atención de urgencias hospitalarias: la acumulación de documentos clínicos no clasificados (órdenes de TC, recetas, epicrisis, laboratorios). 

El sistema clasifica documentos, extrae información médica estructurada bajo estándares internacionales (HL7 FHIR / CIE-11 / NEWS2) y dispara alertas críticas inmediatas (< 60 minutos) ante hallazgos de riesgo vital (como Tromboembolismo Pulmonar o Infarto Agudo de Miocardio), preservando la privacidad del paciente mediante seudonimización previa (RN-M1).

---

## 🏛️ Arquitectura del Monorepo

```text
G10-Equipo20-MediFlow/
├── backend/                  # API FastAPI, LangGraph Agent, PostgreSQL & OCI Storage
│   ├── app/
│   │   ├── api/              # Endpoints REST (documentos, healthcheck)
│   │   ├── core/             # Configuración y base de datos
│   │   ├── graph/            # Grafo determinístico LangGraph
│   │   ├── models/           # Modelos SQLAlchemy
│   │   ├── repositories/     # Capa de persistencia
│   │   ├── schemas/          # Esquemas Pydantic v2
│   │   └── services/         # Storage, validación y orquestación
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                 # Interfaz de Usuario Web (React 19 + TypeScript)
│   ├── src/
│   │   ├── components/       # Modales (Queue Monitor, HL7 FHIR, Impresión)
│   │   │   └── screens/      # Pantallas del flujo (Ingesta, Procesamiento, Cockpit, Alerta Crítica, Revisión Humana, Entrega)
│   │   ├── data/             # Casos de prueba sintéticos (TEP Masivo C1, Apixabán)
│   │   └── types.ts          # Tipado estricto del pipeline
│   ├── Dockerfile
│   └── package.json
│
├── samples/                  # Documentos sintéticos de prueba para ingesta
├── docker-compose.yml        # Orquestación de servicios en contenedores
└── README.md
```

---

## 🎨 Identidad Visual y Paleta Oficial

* **Deep Forest Teal** (`#1E5A52`): Identidad clínica principal.
* **Soft Mint Green** (`#8ED1A4`): Acento ("Flow"), pulso cardíaco ECG y estados activos.
* **Ice White** (`#F6FAF8`): Fondo ergonómico para reducir fatiga visual.
* **Coral Red** (`#E63946`): Alerta crítica inmediata (< 60 min).
* **Warm Amber** (`#E8A238`): Estado de revisión humana asistida.

---

## 🚀 Inicio Rápido (Frontend)

Para levantar la interfaz de usuario en modo local:

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

La aplicación estará disponible en `http://localhost:3000`.

---

## 👥 Equipo 20 — Hackathon ONE G10

* **Frontend & UX:** Marx Villegas ([@vilammarx6-droid](https://github.com/vilammarx6-droid))
* **Backend & Infraestructura:** Bryan Segovia ([@bryan-segovia](https://github.com/bryan-segovia))

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.
