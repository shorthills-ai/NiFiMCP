# NiFi Custom Processors: Email-to-Docx Workflow

This guide introduces **custom NiFi processors** built for an automated pipeline that fetches emails, removes duplicates, generates a DOCX report, and uploads it to OneDrive.

---

### ConvertToDOCX

- **Responsibility**: Converts processed JSON output from LLMs to DOCX format
- **Processor**: NiFi `ExecuteStreamCommand`
- **How it works** : Uses [**Pandoc**](https://pandoc.org/) (CLI tool) internally
- **Input**: JSON data
- **Output**: DOCX format data
- **Dependencies**:
  - Pandoc must be installed on the NiFi host system

---

## Prerequisites

1. **NiFi 2.XX+** installed and running.
2. **Pandoc installed** on the NiFi server.

---

## How to Set Up

1. **Import/Install Processors**: These custom processors must be imported in your NiFi canvas.
2. **Configure Controller Services**:
   - `StandardOAuth2TokenProvider`: Provide Client ID, Secret, and Token Endpoint.
   - Redis-related services for deduplication.
3. **Set Properties**:
- Fill in endpoints, file paths, and credentials in each processor’s properties.

## References

- [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/overview)
- [Pandoc Installation](https://pandoc.org/installing.html)
- [Apache NiFi Documentation](https://nifi.apache.org/docs.html)
