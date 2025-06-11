# 🔄 NiFi Embedding Processor Group Setup

This repository contains a NiFi processor group template for generating text embeddings using either:

- **Amazon Bedrock**
- **Microsoft Azure OpenAI**

---

## 🚀 Getting Started

### 1. Import the Template
- In NiFi, go to the **Operable Canvas**.
- Click on **Upload Template** and select the `.xml` NiFi template file provided in this repo.
- Drag the imported template onto the canvas.

---

## 🧩 Configuration Steps

### 2. Configure `GetFile` Processor
- Open the processor group.
- Locate the `GetFile` processor.
- **Update the Working Directory Path**:
  - Set it to the folder path where your input files (e.g., text chunks) will be read from.

### 3. Configure `ExecuteStreamCommand` Processor
- Still inside the processor group:
  - Open the **`ExecuteStreamCommand`** processor.
  - In the **Properties** tab, click the ➕ icon to add required credentials and parameters.

### 🔐 Required Properties
> ⚠️ Ensure the **names match exactly** and sensitive values are marked as *sensitive*.

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

---

## ⚙️ Parameter Context Configuration

Go to **NiFi → Parameter Contexts**, then either create or edit your context and add the following parameters:

| Parameter Name      | Value Example (Azure / AWS)                    |
|---------------------|------------------------------------------------|
| `EMBEDDING_MODEL`   | e.g., `text-embedding-ada-002` / `amazon.titan-embed-text-v2:0` |
| `EMBEDDING_PROVIDER`| `azure` or `aws`                              |

Set these values based on the provider you're using, as shown below.

---

## 🤖 Supported Providers & Models

### ✅ Microsoft Azure OpenAI

| Parameter         | Value                       |
|------------------|-----------------------------|
| `EMBEDDING_MODEL`| `text-embedding-ada-002`     |
| `EMBEDDING_PROVIDER`| `azure`                  |

**Required Azure Credentials:**
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`

Example:
```env
AZURE_OPENAI_KEY=your_azure_api_key
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=text-embedding-ada-002
AZURE_OPENAI_API_VERSION=2023-05-15
