# Honours-Project-2026: Intelligent Conversational Tutoring Python & Javascript Programming Agent

Aim: Assist students learning Python & Javascript coding through an intelligent conversational agent for programming projects.

## Prerequisites (Will change this when javascript will be implemented)

- Python 3.11
- Node.js 18+
- [Ollama](https://ollama.ai) installed and running
- Code Llama model pulled: `ollama pull codellama`

---

## Quick Start

### 1. Clone and set up the backend

```bash
git clone https://github.com/AshWz-Uni/Honours-Project-2026
cd NLP-AT3-2026

# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
cd ..
uvicorn backend.main:app --reload --port 8000
```

### 2. Set up the frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Ensure Ollama is running with Code Llama

```bash
ollama serve
ollama pull codellama
```

### 4. Open your browser

Navigate to `http://localhost:5173`

---