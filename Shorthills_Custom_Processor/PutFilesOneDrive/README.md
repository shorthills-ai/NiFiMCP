# NiFi Custom Processors: Email-to-Docx Workflow

This guide introduces **custom NiFi processors** built for an automated pipeline that fetches emails, removes duplicates, generates a DOCX report, and uploads it to OneDrive.

---

### PutFilesOneDrive

- **Responsibility**: Uploads the generated DOCX to a target OneDrive folder.
- **Processor**: NiFi `InvokeHTTP`
- **Input**: Trigger request with ODATA String
- **Output**: Files are uploaded to the destination
- **Interface**: `PUT`
- **Custom Variable**:  
  - `ODATA String`: Path to folder where you want to upload files
- **Dependencies**:
  - Microsoft Graph API
  - OAuth2 credentials
- **Controller Service Needed**:
  - `StandardOAuth2TokenProvider`
  - **Properties**:
   - Authorization Server URL : https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/token
   - Client Authentication Strategy : REQUEST_BODY
   - Grant Type : Refresh Token
   - Client ID : <client_id>
   - Client Secret : <client_secret>
   - Scope : App Permissions
   - Refresh Window : 0 s

---

## Prerequisites

1. **NiFi 2.XX+** installed and running.
2. **Microsoft OAuth2 App** registered with access to Outlook and OneDrive APIs.

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
- [Apache NiFi Documentation](https://nifi.apache.org/docs.html)
