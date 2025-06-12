# NiFi Custom Processors: Email-to-Docx Workflow

This guide introduces **custom NiFi processors** built for an automated pipeline that fetches emails, removes duplicates, generates a DOCX report, and uploads it to OneDrive.

---

### DetectDuplication

- **Responsibility**: Deduplicates email records after JSON splitting.
- **Processor**: NiFi `CryptographicHashContent` & `DetectDuplicate`
- **How It Works**:
  - Uses `CryptographicHashContent` processor to assign unique hash to flowfiles
  - Uses `DetectDuplicate` processor to filter out repeated records
- **Input**: Random n number of files
- **Output**: Non-duplicate files
- **Dependencies**:
  - Running Redis(used for tracking seen hashes) instance
- **Controller Services Needed**:
  - `SimpleRedisDistributedMapCacheClientService`
  - `RedisConnectionPoolService`
  - **Properties**:
   - Redis Mode : Standalone
   - Connection String : 127.0.0.1:6379

---

## Prerequisites

1. **NiFi 2.XX+** installed and running.
2. **Redis instance** running and accessible from NiFi (for deduplication).

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
