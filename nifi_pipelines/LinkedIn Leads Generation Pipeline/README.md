# 🚀 EC2 Python Environment Setup & NiFi API Configuration

This guide helps you set up a Python virtual environment on an EC2 server (username/password-based login) and configure NiFi `InvokeHTTP` processors for Lead Discovery, LinkedIn Profile Enrichment, and Recent Posts Collection.

---

## ✅ EC2 Login (Username & Password)

1. SSH into your EC2 instance:

   ```bash
   ssh your-username@your-ec2-ip
   ```

   Example:
   ```bash
   ssh ec2-user@13.234.56.78
   ```

---

## 🐍 Python Virtual Environment Setup

### 1. Install system dependencies

For Ubuntu:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip poppler-utils
```

### 2. Create and activate the virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### 3. Install Python libraries

```bash
pip install pandas requests
```

---

## 🔌 NiFi InvokeHTTP Processor Setup

### ✅ Lead Discovery (POST Method)

- **Method:** `POST`
- **URL:** `https://api.apollo.io/v1/mixed_people/search` (example)
- **Headers:**
  - `X-Api-Key`: `your-api-key`
- **Content-Type:** `application/json`

---

### ✅ LinkedIn Profile Enrichment (GET Method)

- **Method:** `GET`
- **URL:** `https://linkedin-data-api.p.rapidapi.com/?username=${linkedin_username}`
- **Headers:**
  - `x-rapidapi-host`: `linkedin-data-api.p.rapidapi.com`
  - `x-rapidapi-key`: `your-rapidapi-key`

---

### ✅ LinkedIn Recent Posts Collection (GET Method)

- **Method:** `GET`
- **URL:** `https://linkedin-data-api.p.rapidapi.com/get-profile-posts?username=${linkedin_username}`
- **Headers:**
  - `x-rapidapi-host`: `linkedin-data-api.p.rapidapi.com`
  - `x-rapidapi-key`: `your-rapidapi-key`

---

- Replace placeholders like `your-api-key`, `your-rapidapi-key`, and `example_user` with actual values.
