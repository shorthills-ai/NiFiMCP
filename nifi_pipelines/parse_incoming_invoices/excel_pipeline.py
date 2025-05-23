#!/usr/bin/env python3
import os
import sys
import json
import requests
from datetime import datetime, timedelta

CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
FOLDER_ID = os.getenv("FOLDER_ID")
refresh_token = os.getenv("refresh")
# Define the token URL
token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
AUTH_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
SCOPES = ["User.Read", "Mail.Read", "offline_access", "Files.ReadWrite.All"]
data = {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
    "scope": " ".join(SCOPES),  # Replace SCOPES with your required scopes
}
config = {}

with open("config.json", "r") as f:
    config = json.load(f)
token = config.get("token", {}).get("access_token")
token_expiry = config.get("token", {}).get("expires_in", 0)
last_execution = config.get("last_execution")

today = datetime.now()
if today.day >= 15:
    # Use current month and year
    target_date = today
else:
    # Use previous month and year
    # Subtracting 15 days ensures we land in the previous month
    target_date = today - timedelta(days=15)
if not last_execution:
    # Use the previous month and year
    target_date = datetime(today.year, today.month, 15)
    last_execution = target_date.timestamp()
    config["last_execution"] = last_execution
    # Save the updated config
    with open("config.json", "w") as f:
        json.dump(config, f)

if not token or token_expiry < datetime.now():
    # Make the request
    last_execution = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    response = requests.post(token_url, data=data)
    token = response.json()["access_token"]
    token_expiry = datetime.now() + timedelta(seconds=response.json()["expires_in"])
    config["token"]["access_token"] = token
    config["token"]["expires_in"] = token_expiry
    config["last_execution"] = last_execution
    with open("config.json", "w") as f:
        json.dump(config, f)
# Microsoft Graph API endpoints
GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
MONTH_YEAR = target_date.strftime("%b_%Y").upper()

# File naming for May 2025
MANUAL_FILE = f"Invoices_{MONTH_YEAR}.xlsx"
BACKUP_FILE = f"Invoices_BACKUP_{MONTH_YEAR}.xlsx"
PIPELINE_FILE = f"Invoices_PIPELINE_{MONTH_YEAR}.xlsx"

# Excel schema
SCHEMA = [
    "Vendor Name",
    "System Processing Date",
    "Invoice Number",
    "Description",
    "Invoice Date",
    "Total Amount",
    "GST Amount",
    "TDS",
    "Amount Payable",
    "Created By",
]


def get_access_token():
    """Obtain access token using client credentials."""
    payload = {
        "client_id": CLIENT_ID,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }
    response = requests.post(AUTH_URL, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]


def get_file_id(folder_id, file_name, headers):
    """Search for a file in the OneDrive folder by name."""
    base_url = (
        f"{GRAPH_API_URL}/me/drive/items/{folder_id}/children"
        if folder_id
        else f"{GRAPH_API_URL}/me/drive/items/root/children"
    )
    url = base_url
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    files = response.json().get("value", [])
    for file in files:
        if file["name"] == file_name:
            return file["id"]
    return None


def create_excel(folder_id, file_name, headers):
    """Create a new Excel file with the specified schema."""
    try:
        base_url = (
            f"{GRAPH_API_URL}/me/drive/items/{folder_id}/{file_name}/workbook/worksheets"
            if folder_id
            else f"{GRAPH_API_URL}/me/drive/items/root:/{file_name}:/workbook/worksheets"
        )
        url = base_url
        payload = {
            "name": "Sheet1",
            "visibility": "Visible",
            "protection": {"protected": False},
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        # Add schema to the worksheet
        worksheet_id = response.json()["id"]
        table_url = f"{GRAPH_API_URL}/me/drive/items/root:/{file_name}:/workbook/worksheets/{worksheet_id}/range(address='A1:J1')"
        payload = {"values": [SCHEMA]}
        requests.patch(table_url, headers=headers, json=payload).raise_for_status()

        return response.json()["id"]
    except requests.exceptions.RequestException as e:
        print(f"Error in create_excel: {e}")
        raise


def protect_worksheet(item_id, worksheet_id, headers):
    """Apply read-only protection to a worksheet."""
    url = f"{GRAPH_API_URL}/me/drive/items/{item_id}/workbook/worksheets/{worksheet_id}/protection/protect"
    payload = {
        "options": {
            "allowEditObjects": False,
            "allowEditScenarios": False,
            "allowFormatCells": False,
            "allowInsertRows": False,
            "allowDeleteRows": False,
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()


def get_worksheet_data(item_id, worksheet_id, headers):
    """Retrieve all data from a worksheet."""
    url = f"{GRAPH_API_URL}/me/drive/items/{item_id}/workbook/worksheets/{worksheet_id}/usedRange"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("values", [])


def are_sheets_identical(manual_data, backup_data):
    """Compare two worksheet datasets for identical content."""
    if len(manual_data) != len(backup_data):
        return False
    for row1, row2 in zip(manual_data, backup_data):
        if row1 != row2:
            return False
    return True


def get_additional_rows(manual_data, backup_data):
    """Fetch additional rows from manual sheet not in backup."""
    return [row for row in manual_data[1:] if row not in backup_data[1:]]


def append_rows_to_worksheet(item_id, worksheet_id, rows, headers):
    """Append rows to a worksheet."""
    url = f"{GRAPH_API_URL}/me/drive/items/{item_id}/workbook/worksheets/{worksheet_id}/range(address='A1')"
    # Get current row count to append at the end
    used_range = requests.get(url + "/usedRange", headers=headers).json()
    row_count = used_range.get("rowCount", 1)
    append_url = f"{GRAPH_API_URL}/me/drive/items/{item_id}/workbook/worksheets/{worksheet_id}/range(address='A{row_count + 1}')"
    payload = {"values": rows}
    response = requests.patch(append_url, headers=headers, json=payload)
    response.raise_for_status()


def copy_worksheet_data(
    source_item_id, source_worksheet_id, dest_item_id, dest_worksheet_id, headers
):
    """Copy data from source worksheet to destination worksheet."""
    # Get source data
    data = get_worksheet_data(source_item_id, source_worksheet_id, headers)
    # Clear destination worksheet (except header)
    clear_url = f"{GRAPH_API_URL}/me/drive/items/{dest_item_id}/workbook/worksheets/{dest_worksheet_id}/range(address='A2:J1048576')"
    requests.delete(clear_url, headers=headers).raise_for_status()
    # Append data to destination
    append_rows_to_worksheet(dest_item_id, dest_worksheet_id, data, headers)


def main():
    try:
        CLIENT_ID = os.getenv("CLIENT_ID")
        TENANT_ID = os.getenv("TENANT_ID")
        CLIENT_SECRET = os.getenv("CLIENT_SECRET")
        FOLDER_ID = os.getenv("FOLDER_ID")
        refresh_token = os.getenv("refresh")
        # Read JSON input from stdin
        invoice_data = json.load(sys.stdin)

        token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        #        AUTH_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        SCOPES = ["User.Read", "Mail.Read", "offline_access", "Files.ReadWrite.All"]
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(SCOPES),  # Replace SCOPES with your required scopes
        }
        config = {}

        with open("config.json", "r") as f:
            config = json.load(f)
        token = config.get("token", {}).get("access_token")
        token_expiry = config.get("token", {}).get("expires_in", 0)
        last_execution = config.get("last_execution")

        today = datetime.now()
        if today.day >= 15:
            # Use current month and year
            target_date = today
        else:
            # Use previous month and year
            # Subtracting 15 days ensures we land in the previous month
            target_date = today - timedelta(days=15)
        if not last_execution:
            # Use the previous month and year
            target_date = datetime(today.year, today.month, 15)
            last_execution = target_date.timestamp()
            config["last_execution"] = last_execution
            # Save the updated config
            with open("config.json", "w") as f:
                json.dump(config, f)

        if not token or token_expiry < datetime.now():
            # Make the request
            last_execution = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            response = requests.post(token_url, data=data)
            token = response.json()["access_token"]
            token_expiry = datetime.now() + timedelta(
                seconds=response.json()["expires_in"]
            )
            config["token"]["access_token"] = token
            config["token"]["expires_in"] = token_expiry
            config["last_execution"] = last_execution
            with open("config.json", "w") as f:
                json.dump(config, f)
        # Microsoft Graph API endpoints
        # Get access token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
        MONTH_YEAR = target_date.strftime("%b_%Y").upper()

        # File naming for May 2025
        MANUAL_FILE = f"Invoices_{MONTH_YEAR}.xlsx"
        BACKUP_FILE = f"Invoices_BACKUP_{MONTH_YEAR}.xlsx"
        PIPELINE_FILE = f"Invoices_PIPELINE_{MONTH_YEAR}.xlsx"

        # Get or create Excel files
        manual_file_id = get_file_id(FOLDER_ID, MANUAL_FILE, headers)
        backup_file_id = get_file_id(FOLDER_ID, BACKUP_FILE, headers)
        pipeline_file_id = get_file_id(FOLDER_ID, PIPELINE_FILE, headers)

        # If manual file doesn't exist, create all three files
        if not manual_file_id:
            manual_file_id = create_excel(FOLDER_ID, MANUAL_FILE, headers)
            backup_file_id = create_excel(FOLDER_ID, BACKUP_FILE, headers)
            pipeline_file_id = create_excel(FOLDER_ID, PIPELINE_FILE, headers)

        # Get worksheet IDs (assuming single worksheet named 'Sheet1')
        worksheet_url = (
            f"{GRAPH_API_URL}/me/drive/items/{{file_id}}/workbook/worksheets"
        )
        manual_ws_id = requests.get(
            worksheet_url.format(file_id=manual_file_id), headers=headers
        ).json()["value"][0]["id"]
        backup_ws_id = requests.get(
            worksheet_url.format(file_id=backup_file_id), headers=headers
        ).json()["value"][0]["id"]
        pipeline_ws_id = requests.get(
            worksheet_url.format(file_id=pipeline_file_id), headers=headers
        ).json()["value"][0]["id"]

        # Copy manual to backup and protect backup
        copy_worksheet_data(
            manual_file_id, manual_ws_id, backup_file_id, backup_ws_id, headers
        )
        protect_worksheet(backup_file_id, backup_ws_id, headers)

        # Append invoice data to pipeline sheet
        today = datetime.now().strftime("%Y-%m-%d")
        new_rows = [
            [
                invoice.get("VendorName"),
                today,
                invoice.get("InvoiceNumber"),  # Unique invoice number
                "",  # Description (not provided)
                invoice.get("Date"),
                invoice.get("Amount_Payable"),
                invoice.get("GST"),
                invoice.get("TDS"),
                invoice.get("Amount_Payable"),
                "Machine",
            ]
            for invoice in invoice_data
        ]
        append_rows_to_worksheet(pipeline_file_id, pipeline_ws_id, new_rows, headers)

        # Compare manual and backup sheets
        manual_data = get_worksheet_data(manual_file_id, manual_ws_id, headers)
        backup_data = get_worksheet_data(backup_file_id, backup_ws_id, headers)

        if are_sheets_identical(manual_data, backup_data):
            # If identical, copy pipeline data to manual sheet
            copy_worksheet_data(
                pipeline_file_id, pipeline_ws_id, manual_file_id, manual_ws_id, headers
            )
        else:
            # Append additional rows from manual to pipeline
            additional_rows = get_additional_rows(manual_data, backup_data)
            if additional_rows:
                append_rows_to_worksheet(
                    pipeline_file_id,
                    pipeline_ws_id,
                    additional_rows,
                    headers,
                )
    except Exception as e:
        print(f"Error in main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
