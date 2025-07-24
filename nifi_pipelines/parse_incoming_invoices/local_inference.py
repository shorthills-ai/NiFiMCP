from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any
import base64
import tempfile
import os
from docquery import document, pipeline

app = FastAPI()
def map_to_required_format(detailed_data: dict) -> dict:
    """
    Converts a detailed data dictionary into a simpler, standardized format.

    Args:
        detailed_data: A dictionary containing data extracted with specific field names.

    Returns:
        A dictionary with standardized field names.
    """
    # Calculate the total GST amount by summing the components.
    # Use .get(key, 0) to handle cases where a GST type might be missing.
    total_gst = (detailed_data.get("IGST", 0) or 0) + \
                (detailed_data.get("CGST", 0) or 0) + \
                (detailed_data.get("SGST", 0) or 0)

    # Create the new dictionary by mapping old keys to new keys.
    mapped_data = {
        "VendorName": detailed_data.get("VendorName"),
        "Date": detailed_data.get("InvoiceDate"),  # Renamed from InvoiceDate
        "VendorAddress": detailed_data.get("VendorAddress"),
        "GST": total_gst,  # Calculated field
        "GSTIN": detailed_data.get("VendorGstin"), # Renamed from VendorGstin
        "InvoiceNumber": detailed_data.get("InvoiceNumber"),
        "LineItemDescription": detailed_data.get("LineItemDescription"),
        "InvoiceAmt": detailed_data.get("GrossTotal") # Renamed from GrossTotal
    }

    return mapped_data

# Define the expected output schema
EXPECTED_FIELDS = {
    "VendorName": {"type": "STRING", "prompt": "What is the name of the company issuing the invoice?"},
    "VendorAddress": {"type": "STRING", "prompt": "What is the full address of the company issuing the invoice?"},
    "VendorGstin": {"type": "STRING", "prompt": "What is the GSTIN of the vendor/seller, listed under their address?"},
    "CustomerName": {"type": "STRING", "prompt": "What is the name of the 'Bill To' party?"},
    "CustomerAddress": {"type": "STRING", "prompt": "What is the full address of the 'Bill To' party?"},
    "CustomerGstin": {"type": "STRING", "prompt": "What is the GSTIN of the 'Bill To' party?"},
    "InvoiceNumber": {"type": "STRING", "prompt": "What is the Invoice Number?"},
    "InvoiceDate": {"type": "DATE", "prompt": "What is the Invoice Date?"},
    "SubTotal": {"type": "NUMBER", "prompt": "What is the 'SUB TOTAL' amount?"},
    "GrossTotal": {"type": "NUMBER", "prompt": "What is the 'GROSS TOTAL' amount?"},
    "AmountInWords": {"type": "STRING", "prompt": "What is the 'Invoice Amount in Words'?"},
    "LineItemDescription": {"type": "STRING", "prompt": "What is the text under the 'DESCRIPTION OF SERVICES' column?"},
    "LineItemSacCode": {"type": "STRING", "prompt": "What is the code in the 'SAC Code' column?"},
    "LineItemQuantity": {"type": "NUMBER", "prompt": "What is the value in the 'QTY.' column?"},
    "LineItemRate": {"type": "NUMBER", "prompt": "What is the value in the 'RATE (INR)' column?"},
    "GST": {"type": "NUMBER", "prompt": "What is the value in the 'GST (INR)' column?"},
    "LineItemAmount": {"type": "NUMBER", "prompt": "What is the value in the 'AMOUNT (INR)' column?"}
}

# Additional prompts for GST breakdown
GST_BREAKDOWN_PROMPTS = {
    "CGST": "What is the CGST amount?",
    "SGST": "What is the SGST amount?",
    "IGST": "What is the IGST amount?",
}

# Confidence threshold
CONFIDENCE_THRESHOLD = 0.3

class PDFRequest(BaseModel):
    pdf_base64: str

@app.post("/extract_invoice")
def extract_invoice(data: PDFRequest) -> Dict[str, Any]:
    # Decode base64 PDF and save to temp file
    try:
        pdf_bytes = base64.b64decode(data.pdf_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 PDF")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        p = pipeline('document-question-answering',model='impira/layoutlm-invoices')
        doc = document.load_document(tmp_path)
        context = doc.context
        results = {}
        # First, ask all main prompts
        answers = {}
        for field, meta in EXPECTED_FIELDS.items():
            prompt = meta["prompt"]
            res = p(question=prompt, **context)
            print(f"{field}: {res}")
            # res is a dict with 'answer' and 'score' keys
            if isinstance(res, list):
                res = res[0] if res else {}
            if res and res.get('score', 1.0) >= CONFIDENCE_THRESHOLD and res.get('answer'):
                answers[field] = res['answer']
            else:
                answers[field] = None
        mapped_answers = map_to_required_format(answers)
        output = {k: v for k, v in mapped_answers.items() if v is not None}
        return output
    finally:
        os.unlink(tmp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
