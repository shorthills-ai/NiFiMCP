# 🧩 NiFi Text Chunking Processor Group Setup

This repository provides a custom **Apache NiFi** processor group for **text chunking**, enabling you to split raw text into structured segments using multiple chunking strategies:

- **Fixed**
- **Recursive**
- **Semantic**
- **Hybrid**

These chunks are ideal for downstream processes like vector embedding, summarization, or storage in databases.

📦 **Repo**: [https://github.com/shorthills-ai/NiFiMCP](https://github.com/shorthills-ai/NiFiMCP)  
🌿 **Branch**: `dev` → `Shorthills_custom_Processor`

---

## 📦 Components Overview

This processor group includes the following core NiFi processors:

### 1. `GetFile`
- Reads input `.txt` files from a specified directory.
- Configure the input folder path to point to your local text dataset.

### 2. `ExecuteStreamCommand`
- Executes `chunking.py` using Python.
- Accepts input from `GetFile` and emits chunked output.
- Chunking logic is selected based on environment variables.

### 3. `LogAttribute`
- Logs flowfile content and attributes for debugging and verification.

---

## 🚀 Usage Instructions

You can run this chunking setup using either of the following methods:

---

## ✅ Method 1: Quick Setup via JSON Parameters (Recommended)

> This is the fastest and easiest way to use the processor group with minimal customization.

### Steps:

1. Open **Apache NiFi**.
2. Upload the `.json` template via **Upload Template**.
3. Drag the template into the canvas.
4. Update the **Command Path** to the full path of Python inside your virtual environment.
5. Configure **Parameter Context** as shown below.

### 🔐 Required Parameters (used in `ExecuteStreamCommand`)

| Parameter Name       | Description                                           | Sensitive |
|----------------------|-------------------------------------------------------|-----------|
| `CHUNK_TYPE`         | Chunking strategy: `fixed`, `recursive`, `semantic`, `hybrid` | ❌ |
| `CHUNK_SIZE`         | Chunk size in characters (e.g., `500`)               | ❌        |

### ⚙️ Example Parameter Context

| Name         | Value        |
|--------------|--------------|
| `CHUNK_TYPE` | `semantic`   |
| `CHUNK_SIZE` | `500`        |

---

## 🛠 Method 2: Manual Setup on Your Local Machine

This method gives you full flexibility for development and testing.

### Steps:

1. **Clone the repository**
   ```bash
   git clone https://github.com/shorthills-ai/NiFiMCP -b dev
   cd NiFiMCP/Shorthills_custom_Processor
2. **Login to your NiFi machine/server**

3. **Navigate to the processor folder**
   ```bash
    cd ~/nifi2/users/Custom_processor/Chunking
4. **Create a Python virtual environment**
   ```bash
    python3 -m venv chunking
    source chunking/bin/activate
5. **Install dependencies**
   ```bash
   pip install -r requirements.txt
6. **Update ExecuteStreamCommand**
    1. **Change the Command Path to the full path of python inside your virtual environment**

    2. **Change the Working Directory to where chunking.py exists (e.g., ~/nifi2/users/Custom_processor/Chunking)**
7. **Rest the configuration of execute stream command and parameter context setup is same as in Method 1.**

    