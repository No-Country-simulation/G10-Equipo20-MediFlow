# MediFlow — Cómo correr el proyecto en Windows

Guía paso a paso para levantar el proyecto en tu computadora local, sin Docker y sin PostgreSQL.

---

## 1. Requisitos previos

Necesitas tener instalado:

| Herramienta | Versión probada | Para qué |
|---|---|---|
| **Git** | 2.54.0 | Traer el código |
| **Python** | 3.12.10 | El backend (FastAPI + LangGraph) |
| **Node.js** | 24.19.0 | El frontend (React + Vite) |

Para comprobarlo, abre PowerShell y ejecuta:

```powershell
git --version
python --version
node --version
npm --version
```

Si alguno no aparece, instálalo antes de seguir.

---

## 2. Traer el código

```powershell
cd $HOME\Documents
git clone https://github.com/No-Country-simulation/G10-Equipo20-MediFlow.git
cd G10-Equipo20-MediFlow
git checkout marx-villegas
```

---

## 3. Configurar el backend

El backend lee su configuración desde `backend/.env`. Ese archivo **nunca se sube al repo** (está en `.gitignore`), así que cada quien crea el suyo.

Copia el ejemplo y edítalo:

```powershell
cd backend
copy .env.example .env
notepad .env
```

Cambia estas líneas para trabajar en local **sin PostgreSQL y sin Docker**:

```ini
# Base de datos local en un archivo. Alternativa a PostgreSQL para desarrollo.
DATABASE_URL=sqlite:///./mediflow.db

# Desactiva el bucle de escalamiento de alertas en segundo plano.
# Con SQLite ese bucle genera bloqueos y las peticiones quedan colgadas.
escalamiento_cada_s=0
```

> ⚠️ **Por qué SQLite y no PostgreSQL**
> El proyecto está diseñado para PostgreSQL (lo dice `docker-compose.yml`), pero SQLite no
> maneja bien varias peticiones simultáneas. El bucle de alertas que corre en segundo plano
> cada 60 segundos saturaba la base de datos y el backend cortaba las conexiones
> (`ECONNRESET`), dejando el botón de "Ingresar" congelado.
> Con `escalamiento_cada_s=0` eso se resuelve y todo funciona local.

El resto de variables (OpenAI, Gemini, OCI, Slack) se pueden dejar vacías para probar la interfaz.

### Instalar dependencias del backend

```powershell
python -m pip install -r requirements.txt
```

---

## 4. Configurar el frontend

```powershell
cd ..\frontend
npm install
```

> No hay que cambiar nada. El frontend habla con Vite en el puerto 5173 y Vite le reenvía las
> peticiones al backend en el puerto 8000. **No cambies `BASE_URL` en `src/api.ts`**, déjalo como
> `"/api"`: si lo apuntas directo al backend, el navegador bloquea la cookie de sesión y la app
> saca al usuario apenas entra.

---

## 5. Levantar los dos servidores

Necesitas **dos ventanas de PowerShell separadas**.

### Ventana 1 — Backend (puerto 8000)

```powershell
cd $HOME\Documents\G10-Equipo20-MediFlow\backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Espera a ver: `Application startup complete.`

### Ventana 2 — Frontend (puerto 5173)

```powershell
cd $HOME\Documents\G10-Equipo20-MediFlow\frontend
npm run dev
```

Espera a ver: `VITE ready in ...`

---

## 6. Entrar

Abre en el navegador:

- **Aplicación:** <http://localhost:5173>
- **API (Swagger):** <http://localhost:8000/docs>

La primera vez, la base de datos está vacía, así que la pantalla de ingreso ofrece **crear el
primer administrador**:

| Campo | Valor sugerido |
|---|---|
| Usuario | `admin` |
| Nombre | tu nombre |
| Clave | mínimo 8 caracteres, con letras **y** números (ej. `mediflow2026`) |

### Ver todas las secciones (Documentos, Revisión, Alertas…)

El rol `administrador` **no ve datos clínicos** por diseño (regla RN-K2). Para ver la parte
clínica, crea una cuenta con rol **Auditor clínico** desde `Administración → Usuarios`, cierra
sesión e ingresa con esa cuenta.

---

## 7. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| El botón "Ingresar" se queda en *Ingresando…* | El bucle de alertas saturó SQLite | `escalamiento_cada_s=0` en `.env` y reiniciar el backend |
| El navegador entra y al instante sale | La cookie de sesión no viaja | Verifica que `BASE_URL = "/api"` en `frontend/src/api.ts` |
| `/docs` sale en blanco | Swagger carga librerías de internet | Usa `http://localhost:8000/openapi.json` o abre el JSON directo |
| `address already in use` | Ya hay algo en ese puerto | Cierra la otra terminal o cambia el puerto |
| La base de datos quedó corrupta | Apagaste el servidor a la fuerza | Borra `backend/mediflow.db` y vuelve a arrancar (se recrea sola) |
| Faltan pacientes o documentos | Empezaste limpio | El botón **Cargar un caso de ejemplo** de la pantalla Documentos carga datos de prueba |

---

## 8. Correr las pruebas

```powershell
cd $HOME\Documents\G10-Equipo20-MediFlow\backend
python -m pytest
```

Las pruebas usan SQLite en memoria, así que no tocan tu base local.

---

## 9. Casos de prueba del hackathon

En la carpeta `samples/` están los seis casos que usa el proyecto para demostrar el flujo:

| Archivo | Escenario |
|---|---|
| `caso01_tc_torax_tep.txt` | **Urgencia médica** (tromboembolismo pulmonar) |
| `caso02_formula_losartan.txt` | **Flujo estándar** (receta de rotina) |
| `caso03_formula_apixaban.txt` | **Flujo estándar** (receta de rutina) |
| `caso04_orden_eco_estres_sin_justificacion.txt` | **Ambiguo** (pide revisión humana) |
| `caso05_orden_cateterismo_urgencias.txt` | Derivación a urgencias |
| `caso06_cc_invalida.txt` | **Ambiguo** (documento incompleto) |

En `samples/archivos/` hay además PDFs e imágenes (`ambiguous.png`, `documento_sintetico.pdf`,
`cardio_scan.jpg`) para probar la lectura de archivos y no solo texto.

Se pueden cargar desde **Documentos → Cargar un caso de ejemplo**.

---

## 10. Para detener los servidores

En cada ventana de PowerShell, presiona `Ctrl + C`.
