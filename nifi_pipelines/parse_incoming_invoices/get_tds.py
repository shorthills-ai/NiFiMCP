
def main():
    import sys
    import csv
    import json
    import os

    # Read JSON from stdin
    input_json = sys.stdin.read()
    try:
        invoice_data = json.loads(input_json)
    except Exception as e:
        print("Invalid JSON input:", e)
        return

    vendor_name = invoice_data.get("VendorName")
    tds_rate = None

    # Read CSV file from current directory
    csv_file = None
    for fname in os.listdir('.'):
        if fname.endswith('.csv'):
            csv_file = fname
            break

    if not csv_file:
        print("CSV file not found in current directory.")
        return

    with open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            if row.get("Vendor Name", "").strip() == vendor_name:
                tds_rate_str = row.get("TDS Rate", "").replace('%', '').strip()
                try:
                    tds_rate = float(tds_rate_str) / 100.0
                except:
                    tds_rate = 0.0
                break

    if tds_rate is None:
        tds_rate = 0.0

    invoice_amt = invoice_data.get("InvoiceAmt", 0)
    gst_amt = invoice_data.get("GST", 0)

    tds_amount = round(invoice_amt * tds_rate, 2)
    total_payable = round((invoice_amt - tds_amount) + gst_amt, 2)

    invoice_data["TDSAmount"] = tds_amount
    invoice_data["TotalPayable"] = total_payable

    print(json.dumps(invoice_data, indent=2))
   
    
if __name__ == "__main__":
    main()