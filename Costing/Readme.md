# 📊 Query API with Token Costing

This project sets up a FastAPI-based service to handle file uploads, process embeddings using Azure OpenAI, and store/query data in Weaviate. The response includes both the query results and detailed token/cost analysis.

---

## 🚀 Features

- Upload and query text from `.docx`, `.pptx`, or other supported formats
- Embedding with Azure OpenAI
- Vector search with Weaviate
- Returns both the AI-generated response and cost breakdown (tokens + pricing)

---

## 🛠️ Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/shorthills-ai/NiFiMCP
cd NiFiMCP
Switch to dev server.
```

### 2. create an environment
```bash
python3 -m venv venv
source venv/bin/activate 
```

## 3. Install the requirements.
```bash
pip install -r requirements.txt
```

## 4. Configure the .env file
```bash
DRIVE_ID=your_drive_id # not important for costing
WEAVIATE_URL=your_weaviate_url
WEAVIATE_API_KEY=your_weaviate_api_key
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
EMBEDDING_MODEL=text-embedding-ada-002
```

## Run the Script 
```bash
python3 rag_costing.py
```
