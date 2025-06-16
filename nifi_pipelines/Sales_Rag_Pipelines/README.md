# 🧠 RAG Pipeline with NiFi and Redis Integration

This repository provides a Retrieval-Augmented Generation (RAG) pipeline that uses **Apache NiFi** for orchestration, **Redis** for monitoring incoming files, and **Weaviate** for vector database storage. It is designed to fetch all files recursively from a specified folder in OneDrive (using Microsoft Graph API), index them using an embedding model, and make them queryable. Users can ask questions via **Microsoft Teams**, and the relevant answers are retrieved from indexed content and returned to the user.

---

## ⚙️ Overview

### 🔁 Workflow Summary

1. **Fetch Files**: Recursively fetch files from a OneDrive folder using Microsoft Graph API (`folder_id`).
2. **Monitor Changes**: Use Redis to detect new incoming files continuously.
3. **Indexing**: Files are processed and indexed via Azure OpenAI embedding models.
4. **Storage**: Embeddings are stored in Weaviate DB.
5. **Querying**: When a user sends a question from Microsoft Teams, the system searches Weaviate and responds with the most relevant information.

---

## 🚀 Method 1: Setup via NiFi Template

### 📥 Upload Template

1. Upload the `sales_indexing.json` template to your Apache NiFi instance.

### 🔧 Configure Reference Parameters

Set the following **8 reference parameters** in NiFi before running the pipeline:

| Parameter Name          | Description                         |
|-------------------------|-------------------------------------|
| `access_token`          | Microsoft Graph API access token    |
| `embedding_service_url` | URL for the embedding service       |
| `extraction_service_url`| URL for text/file extraction API    |
| `folder_id`             | OneDrive folder ID to index         |
| `graph_api_base`        | Base URL for Microsoft Graph API    |
| `weaviate_api_key`      | API Key for Weaviate                |
| `weviate_service_url`   | URL of the Weaviate instance        |
| `drive_id`              | Drive ID from Microsoft OneDrive    |

---

## 🧪 Method 2: Manual Execution (via Python)

1. **Clone the GitHub repository**:

   ```bash
   git clone https://github.com/shorthills-ai/NiFiMCP
2. **git checkout dev and relevant folder**
    ```bash
    git checkout dev
    cd nifi_pipelines/Sales_Rag_Pipeline
3. **Create and activate a virtual environment**
    ```bash
    python3 -m venv my_env_name
    source my_env_name/bin/activate
4. **Install Dependencies**
    ```bash
    pip install -r requirements.txt
5. **Run the RAG script:**
    ```bash
    python3 rag.py
6. **Set up the NiFi pipeline as described in Method 1.**


