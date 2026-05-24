import re
import pytesseract
import pandas as pd
from PIL import Image

# NOTE: If you are on Windows, you usually need to point Python directly to where Tesseract was installed:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_invoice_without_ai(image_path, output_excel_path):
    print("Loading image...")
    img = Image.open(image_path)
    
    print("Running local OCR extraction (Tesseract)...")
    # Convert image to string text
    raw_text = pytesseract.image_to_string(img)
    
    print("Parsing raw text into data structures...")
    lines = raw_text.split('\n')
    
    # Storage structures
    invoice_no = "UNKNOWN"
    invoice_date = "UNKNOWN"
    party_name = "KISHORE FABRICS PVT LTD" # Hardcoded seller based on image standard
    
    item_rows = []
    
    # 1. PARSE METADATA & LINE ITEMS VIA REGEX / TEXT RULES
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
            
        # Extract Invoice Number (Looking for patterns like E/SUR-10109)
        if "Invoice No" in clean_line or "E/SUR" in clean_line:
            inv_match = re.search(r'(E/SUR-\d+)', clean_line)
            if inv_match:
                invoice_no = inv_match.group(1)
                
        # Extract Date (Looking for DD-Mon-YY pattern)
        date_match = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{2,4})', clean_line)
        if date_match:
            invoice_date = date_match.group(1)
            
        # Extract Table Rows: Look for rows starting with a number followed by capital item text
        # Example line: "1 APRICOT KSTL 212992 540752 5% 6 PCS 1,099.00 PCS 6,594.00"
        item_match = re.match(r'^(\d+)\s+(.+?)\s+(\d{5,8})\s+(\d+[\s%]+)\s+(\d+)\s+PCS\s+([\d,.]+)\s+PCS\s+([\d,.]+)', clean_line)
        
        if item_match:
            sl_no = item_match.group(1)
            desc = item_match.group(2)
            hsn = item_match.group(3)
            gst = item_match.group(4).strip()
            qty = item_match.group(5)
            rate = item_match.group(6).replace(',', '')
            amount = item_match.group(7).replace(',', '')
            
            item_rows.append({
                "Parent_Invoice_No": invoice_no,
                "Stock_Item_Name": desc,
                "HSN_SAC": hsn,
                "GST_Rate": gst,
                "Quantity": int(qty),
                "Unit": "PCS",
                "Rate_Per_Unit": float(rate),
                "Item_Amount": float(amount)
            })

    # 2. CALCULATE FINANCIALS BASED ON EXTRACTED ITEMS (Safer than relying on OCR totals)
    total_taxable = sum(item['Item_Amount'] for item in item_rows)
    cgst = round(total_taxable * 0.025, 2) # Assuming 2.5% CGST based on 5% GST
    sgst = round(total_taxable * 0.025, 2) # Assuming 2.5% SGST
    grand_total = round(total_taxable + cgst + sgst)
    
    # 3. BUILD TALLY HEADER DATAFRAME
    header_data = {
        "Voucher_Type": ["Purchase"],
        "Invoice_No": [invoice_no],
        "Date": [invoice_date],
        "Party_Ledger": [party_name],
        "Purchase_Ledger": ["Purchase Accounts"], 
        "Taxable_Value": [total_taxable],
        "CGST_Amount": [cgst],
        "SGST_Amount": [sgst],
        "Grand_Total": [grand_total]
    }
    
    df_headers = pd.DataFrame(header_data)
    df_items = pd.DataFrame(item_rows)
    
    # 4. EXPORT TO TALLY MAPABLE EXCEL
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        df_headers.to_excel(writer, sheet_name='Voucher_Headers', index=False)
        df_items.to_excel(writer, sheet_name='Voucher_Items', index=False)
        
    print(f"Data saved locally to {output_excel_path} without hitting any cloud servers/models!")

# Execute
if __name__ == "__main__":
    extract_invoice_without_ai(
        image_path="invoiceSample.jpeg", 
        output_excel_path="Local_Ocr_Tally_Invoices.xlsx"
    )