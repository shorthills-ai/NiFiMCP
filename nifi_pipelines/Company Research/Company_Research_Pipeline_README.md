# Company Research Sales Pipeline

This Apache NiFi pipeline automates the end-to-end **company research process** by fetching research request emails from Outlook, deduplicating them, generating DOCX reports, and uploading them to OneDrive.

---

## Overview

### Key Capabilities

- **Automated polling** of Outlook inbox for new research requests
- **Deduplication** using cryptographic hashes & Redis
- **Conversion** of structured research into DOCX format using Pandoc
- **Upload** final reports to OneDrive via Microsoft Graph API

---

## Pipeline Architecture

```
[GenerateFlowFile]
        ↓
[FetchOutlookEmails] 
        ↓
[SplitEmails (SplitJSON)]
        ↓
[DetectDuplication (SHA-256 + Redis)]
        ↓
[ExtractBodyContent (EvaluaetJSONPath)]
        ↓
[PrepareText (ReplaceText)]
        ↓
[PreparePayload (ExecuteScript)]
        ↓
[CallLLM (InvokeHTP)]
        ↓
[ExtractResult (EvaluaetJSONPath)]
        ↓
[ConvertToDOCX using Pandoc]
        ↓
[Upload to OneDrive]
```

---

## Custom Processors & Modules

### 1. **FetchOutlookEmails**
- **Purpose**: Connects to Microsoft Outlook via Microsoft Graph and fetches emails matching a filter.
- **Processor**: `InvokeHTTP`
- **Method**: `GET`
- **Filter Example**:  
  `?$filter=from/emailAddress/address eq 'xyz@domain.com' and contains(subject,'Research Request')`
- **Dependencies**:
  - Microsoft Graph API
  - OAuth2 access token (via `StandardOAuth2TokenProvider`)

### 2. **DetectDuplication**
- **Purpose**: Deduplicates emails to avoid redundant processing.
- **Processors Used**:  
  - `CryptographicHashContent` (generates SHA-256)
  - `DetectDuplicate` (with Redis cache)
- **Redis Services Required**:
  - `SimpleRedisDistributedMapCacheClientService`
  - `RedisConnectionPoolService`

### 3. **ConvertToDOCX**
- **Purpose**: Converts JSON or markdown data to `.docx` using `pandoc`
- **Processor**: `ExecuteStreamCommand`
- **Command**:
  ```bash
  /bin/bash -c "pandoc -f markdown -t docx -o -"
  ```
- **Dependency**: Pandoc must be installed on the NiFi server.

### 4. **PutFilesOneDrive**
- **Purpose**: Uploads the final DOCX report to a predefined OneDrive path.
- **Processor**: `InvokeHTTP`
- **Method**: `PUT`
- **Target URL**:
  ```
  https://graph.microsoft.com/v1.0/me/drive/root:/presales/${company}_Research/Research.docx:/content
  ```
- **Requires**:
  - OAuth2 token (via `StandardOAuth2TokenProvider`)
  - Proper OneDrive path variables (e.g., `${company}`)

---

## Setup Instructions

### Prerequisites

1. Apache NiFi 2.x installed and running
2. Pandoc installed on the NiFi server
3. Microsoft Azure App Registration
   - App must have permissions for Outlook and OneDrive APIs
4. Redis server running (default at `127.0.0.1:6379`) for deduplication

### Configuration Steps

1. **Import JSON**:
   - Import `Company_Research_Pipeline.json` in your NiFi canvas.

2. **Configure OAuth2**:
   - Create and enable a `StandardOAuth2TokenProvider` controller service.
   - Set:
     - `Authorization Server URL`: `https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/token`
     - `Client ID`, `Secret`
     - `Grant Type`: `Refresh Token`
     - `Scope`: Required Microsoft Graph scopes

3. **Configure Redis (for Deduplication)**:
   - Enable:
     - `SimpleRedisDistributedMapCacheClientService`
     - `RedisConnectionPoolService`
   - Set:
     - Redis Host: `127.0.0.1`
     - Redis Port: `6379`

4. **Pandoc Installation**:
   - Install Pandoc on the host system:
     ```bash
     sudo apt install pandoc
     ```

---

## Sample Test

1. Send a test research request email.
2. Start the flow from the 'GenerateFlowFile' trigger.
3. The DOCX will be created and uploaded to:
   ```
   OneDrive/presales/<CompanyName>_Research/Research.docx or any other custom folder you want.
   ```

---

## References

- [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/overview)
- [Pandoc Documentation](https://pandoc.org/)
- [Apache NiFi Docs](https://nifi.apache.org/docs.html)

