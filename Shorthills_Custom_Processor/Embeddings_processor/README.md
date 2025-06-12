# 🔄 NiFi Embedding Processor Group Setup

This repository provides a custom NiFi processor group for generating **text embeddings** using:

- **Amazon Bedrock**
- **Microsoft Azure OpenAI**

The processor reads input text files, generates embeddings via the selected cloud provider, and logs output for downstream processing.

Repo: [https://github.com/shorthills-ai/NiFiMCP](https://github.com/shorthills-ai/NiFiMCP)  
Branch: `dev` → `Shorthills_custom_Processor`

---

## 📦 Components Overview

The processor group contains the following core NiFi components:

### 1. `GetFile`
- Reads input `.txt` files from a specified directory.
- Configurable input path.
- **Set Working Directory** to your local folder containing text chunks.

### 2. `ExecuteStreamCommand`
- Executes the `embeddings.py` script using Python to generate embeddings.
- Accepts input from `GetFile`.
- Requires environment variables (API keys, model names) configured as properties.

### 3. `LogAttribute`
- Logs output from `ExecuteStreamCommand`.
- Useful for verifying embeddings and flowfile attributes.

---

## 🚀 Usage Instructions

You can run this setup using either of the two methods:

---

## ✅ Method 1: Quick Setup via JSON Parameters (Recommended)

> Only update API keys and model info in parameter context.

### Steps:

1. Open NiFi.
2. Upload the `.xml` template via **Upload Template** in the Operable Canvas.
3. Drag the template into the canvas.
4. Mention the location of your python in the command path
4. Configure Parameter Context with the following:

### 🔐 Required Properties (in `ExecuteStreamCommand`)
| Property Name                | Description                                 | Sensitive |
|-----------------------------|---------------------------------------------|-----------|
| `AWS_ACCESS_KEY_ID`         | Amazon Bedrock access key                   | ✅        |
| `AWS_SECRET_ACCESS_KEY`     | Amazon Bedrock secret key                   | ✅        |
| `AWS_REGION`                | AWS region (e.g., `us-east-1`)              | ❌        |
| `AZURE_OPENAI_KEY`          | Azure OpenAI API key                        | ✅        |
| `AZURE_OPENAI_ENDPOINT`     | Azure OpenAI endpoint URL                   | ✅        |
| `AZURE_OPENAI_DEPLOYMENT`   | Azure model deployment name                 | ✅        |
| `AZURE_OPENAI_API_VERSION`  | Azure API version (e.g., `2023-05-15`)      | ✅        |
| `EMBEDDING_MODEL`           | Set as `#{EMBEDDING_MODEL}`                | ❌        |
| `EMBEDDING_PROVIDER`        | Set as `#{EMBEDDING_PROVIDER}`             | ❌        |

### ⚙️ Parameter Context

Go to **NiFi → Parameter Contexts**, then add:

| Parameter Name      | Value Example                                   |
|---------------------|-------------------------------------------------|
| `EMBEDDING_MODEL`   | `text-embedding-ada-002` or `amazon.titan-embed-text-v2:0` |
| `EMBEDDING_PROVIDER`| `azure` or `aws`                                |

---

## 🛠 Method 2: Setup on Your Own Machine

This method allows full customization and local script execution.

### Steps:

1. **Clone the repository**  
   ```bash
   git clone https://github.com/shorthills-ai/NiFiMCP -b dev
   cd NiFiMCP/Shorthills_custom_Processor
2. **Login to your NiFi machine/server**

3. **Navigate to the processor folder**
   ```bash
    cd ~/nifi2/users/Custom_processor/Embeddings
4. **Create a Python virtual environment**
   ```bash
    python3 -m venv embeddings
    source embeddings/bin/activate
5. **Install dependencies**
   ```bash
   pip install -r requirements.txt
6. **Update ExecuteStreamCommand**
    1. **Change the Command Path to the full path of python inside your virtual environment**

    2. **Change the Working Directory to where embeddings.py exists (e.g., ~/nifi2/users/Custom_processor/Embeddings)**
7. **Rest the configuration of execute stream command and parameter context setup is same as in Method 1.**

    