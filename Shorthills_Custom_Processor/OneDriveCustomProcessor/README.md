# NiFi Pipeline: Recursively List and Process OneDrive Files

This NiFi flow enables recursive listing of files from a OneDrive folder, then performs an action based on user input — **viewing metadata** or **downloading files**. Files can be downloaded to either **local storage** or another **OneDrive folder**.

---

## Prerequisites

- Apache NiFi 2.4.0
- Microsoft Azure account with OneDrive access
- Access Token for Microsoft Graph API


---

## Overview

This NiFi flow:
1. Recursively Lists All Files from a OneDrive folder using Microsoft Graph API.
2. Routes Files Based on **user action** (`view` or `download` or `both`) provided through parameters.
3. Executes Action:
   - If `view`: shows metadata (name, size, type, web URL)
   - If `download`:
     - **To local**: Downloads to given directory path
     - **To onedrive**: Copies files to a target OneDrive folder
   - If `both` : shows metadata as well as performs download operation

---

## Parameter Contexts Used

| Parameter Name       | Description                                      |
|----------------------|--------------------------------------------------|
| `access_token`       | Bearer token for Microsoft Graph API             |
| `source_folder_id`| ID of the OneDrive folder to start from |
| `source_drive_id`        | Drive ID of the source folder          |
| `target`    | Target of the download action ( `local` to store on disk, `onedrive` to upload to another OneDrive folder) |
| `action`   | Determines the flow path, Set `view` or `download` or `both` |
|`target_drive_id`  | Drive ID where files should be uploaded  |
|`target_folder_id` | Folder ID in the target drive |

> ⚠️ **Note**: The output directory path for saving files locally is configured directly inside the `PutFile` processor.

---
## Steps to Run the Flow

### 1. Import NiFi Flow

1. Open your NiFi instance.
2. Go to the canvas and click on **Create one Processor Group**.
3. Upload the `custom_onedrive_NIFI.json` file provided.


> 📝 This template is already connected to a Parameter Context named `Parameters_custom_onedrive`.

---

### 2. Set Parameter Values

- Go to **Parameter Contexts**.
- Locate and edit the context named `Parameters_custom_onedrive`.
- Set all the parameters.


### 3. Start the Flow

- Right-click on the root process group and select **Start**.
- The flow will trigger automatically and:
   - Recursively list files from the OneDrive folder.
   - Route and execute based on user intent (view or download).

No additional configuration is needed — everything else is wired up in the template.

## 📁 Get Drive ID and Folder ID from Folder Path

To run the NiFi pipeline, you will need the **Drive ID** and **Folder ID** of your OneDrive folder. Follow these steps to get them using the **Microsoft Graph API**.

---

### 🔍 Get Encoded Folder Path, Drive ID & Folder ID (from Folder URL)

#### Step 1: Copy the Folder URL

Example URL : https://shorthillstech-my.sharepoint.com/:f:/g/personal/rakhee_prajapat_shorthills_ai/EtPikH9Sz7NDnAozKcb9nIcB4r3nM_3tYJKDPQZC_qdRjw


---

#### Step 2: Encode Folder URL in Terminal

Replace `<FOLDER_URL>` below with your copied OneDrive folder URL (in double quotes):

```bash
echo -n "<FOLDER_URL>" | base64 | tr '+/' '-_' | tr -d '='
```

This returns the encoded_folder_path used for the Microsoft Graph API.

#### Step 3: Get Drive ID & Folder ID using curl

Replace:

    <ACCESS_TOKEN> with your valid Microsoft Graph API token

    <ENCODED_FOLDER_PATH> with the value obtained in Step 2

```bash

curl -X GET \
  "https://graph.microsoft.com/v1.0/shares/u!<ENCODED_FOLDER_PATH>/driveItem" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Accept: application/json"
```

Response

The response will be a JSON object. Look for:

    "parentReference": { "driveId": "<YOUR_DRIVE_ID>" }

    "id": "<YOUR_FOLDER_ID>"

Use these in your NiFi pipeline configuration.


