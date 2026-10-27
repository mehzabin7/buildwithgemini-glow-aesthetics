# ✨ GlowAesthetics Clinic Concierge

> An intelligent, clinical-grade aesthetic concierge powered by Google Agent Development Kit (ADK), Gemini, and Vertex AI.

![GlowAesthetics Demo](demo.gif)

---

## 🌟 Overview

**GlowAesthetics Clinic Concierge** helps clients analyze skin concerns, discover clinical aesthetic treatments, triage contraindications, and plan personalized consultation schedules.

### Key Capabilities
- **Cross-Session Memory:** Powered by **Vertex AI Memory Bank**, remembering client skin profile (Fitzpatrick skin type, sensitivity), current active ingredients (tretinoin, AHA/BHAs), medical contraindications, and allergy history across sessions.
- **Clinical Catalog & A2UI:** Renders aesthetic treatments (HydraFacial, RF Microneedling, Chemical Peels, Laser Resurfacing, Dermal Fillers) as rich **A2UI** cards detailing pricing, downtime, target concerns, and preparation steps.
- **Clinical Tools & Safety Checks:**
  - `list_treatments` / `get_treatment_details`: Firestore-backed treatment catalog with contraindication checks.
  - `check_active_ingredient_safety`: Validates active ingredients against planned procedures.
  - `get_local_uv_and_sun_safety`: Live Open-Meteo UV index API for post-procedure sun-safety advice.
  - `geocode_address` / `search_nearby_places`: Google Maps APIs for finding partner clinic locations.
  - `book_consultation` / `get_consultation`: Schedules consultations with practitioners in Firestore.
- **Multimodal Visual Previews:**
  - `generate_treatment_image`: Personalized visual skincare protocol and treatment preview cards using `gemini-3.1-flash-lite-image`.
  - `generate_treatment_video`: Short aesthetic treatment clips using Google Omni model (`gemini-omni-flash-preview`) in the `global` region, saved to Cloud Storage and Agent Platform artifacts.
- **Agent Engine Sandbox:** Executes Python code in a secure sandbox to calculate multi-session package pricing, 12-week treatment timeline intervals, and bespoke discount bundles.
- **Luxury Web Frontend:** Custom FastAPI proxy talking over the **A2A protocol** with a luxury rose-gold medical aesthetic chat interface.

---

## 🏗️ Architecture

```
User (Browser)
      │
      ▼
Cloud Run (FastAPI A2A Proxy + Static Chat UI)
      │  (A2A Protocol / gRPC)
      ▼
Vertex AI Agent Platform (Reasoning Engine / ADK Agent)
      ├── Vertex AI Memory Bank (Long-term client memory)
      ├── Firestore Database (Treatments, Schedules, Bookings)
      ├── Cloud Storage Bucket (Generated images & Omni videos)
      ├── Agent Engine Code Sandbox (Pricing & interval math)
      ├── Gemini 2.5 Flash / Gemini Omni (Reasoning & Multimodal)
      └── External APIs (Google Maps, Open-Meteo UV Index)
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) package manager
- [`agents-cli`](https://google.github.io/agents-cli/)
- Google Cloud SDK (`gcloud`)

### 1. Installation
```bash
git clone <your-repo-url>
cd glow-aesthetics
uv sync
```

### 2. Local Development (ADK Web Playground)
```bash
uv run adk web . --port 8080
```
Open `http://localhost:8080` to interact with the agent in the ADK Developer UI.

### 3. Running the Frontend Proxy Locally
```bash
cd frontend
export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_ID>/locations/<REGION>/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 📦 Deployment

### Deploying the Agent to Agent Platform
```bash
agents-cli deploy
```

### Deploying the Frontend to Cloud Run
```bash
gcloud run deploy glow-aesthetics-frontend \
  --source ./frontend \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars "AGENT_ENGINE_RESOURCE_NAME=<RESOURCE_NAME>,AGENT_DIRECTORY=app"
```

---

## 📄 License
Apache 2.0
