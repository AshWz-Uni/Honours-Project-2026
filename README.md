# NLP-AT3-2026
Assignment Task 3 for Introduction to Natural Language Processing 
# NLP Project: Python Coding FAQ Agent

Aim: Assist students learning Python coding through an intelligent agent for programming projects.

## Prerequisites

- Python 3.11
- Node.js 18+
- [Ollama](https://ollama.ai) installed and running
- Code Llama model pulled: `ollama pull codellama`

---

## Quick Start

### 1. Clone and set up the backend

```bash
git clone https://github.com/AshWz-Uni/NLP-AT3-2026.git
cd NLP-AT3-2026

# Install Python dependencies
cd backend
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