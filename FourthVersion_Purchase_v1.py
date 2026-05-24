import os
import json
import pandas as pd
from PIL import Image
from pydantic import BaseModel, Field
from typing import List, Optional
from google import genai
from google.genai import types

# =====================================================================
# 1. FIXED DATA SCHEMA WITH SUPPLIER ADDRESS AND PINCODE
# =====================================================================
class InvoiceItem(BaseModel):
    description_of_goods: str = Field(description="The name or description of the stock item")
    hsn_sac: str = Field(description="HSN or SAC code")
    gst_rate: str = Field(description="GST percentage rate applied as a string (e.g., 5%)")
    quantity: int = Field(description="Quantity unit count")
    rate: float = Field(description="Rate per piece/unit excluding tax")
    amount: float = Field(description="Total item value before tax (Quantity * Rate)")

class TallyInvoiceSchema(BaseModel):
    invoice_no: str = Field(description="Unique Tax Invoice Number (e.g., E/SUR-10109)")
    invoice_date: str = Field(description="Date of invoice converted to DD-MM-YYYY format")
    party_ledger_name: str = Field(description="The seller/supplier business name (e.g., KISHORE FABRICS PVT LTD)")
    supplier_address: str = Field(description="Full physical address of the supplier/seller as a single string line")
    supplier_pincode: str = Field(description="Extract the 6-digit postal pincode from the supplier address block (e.g., 522501)")
    gstin: str = Field(description="GSTIN of the supplier/seller (e.g., 37AACCK9514G1ZG)")
    
    total_taxable_value: float = Field(description="Sum total of item amounts before tax (e.g., 39959.00)")
    hamali_charges: float = Field(default=0.0, description="The explicit Hamall Charges value found under the items table (e.g., 120.00)")
    cgst_amount: float = Field(description="The exact Outward CGST amount summary value written on the invoice (e.g., 1001.98)")
    sgst_amount: float = Field(description="The exact Outward SGST amount summary value written on the invoice (e.g., 1001.98)")
    round_off: float = Field(default=0.0, description="Invoice rounding balance variation amount (e.g., 0.04)")
    grand_total: float = Field(description="Final net total payable value of invoice (e.g., 42083.00)")
    
    line_items: List[InvoiceItem] = Field(description="List of all stock line items split in rows")

# =====================================================================
# 2. RUN EXTRACTION AND ROW POSITION DISTRIBUTION LOGIC
# =====================================================================
def extract_and_convert_to_exact_tally_format(image_path: str, output_excel_path: str):
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("Please set your GEMINI_API_KEY environment variable.")
    
    client = genai.Client()
    img = Image.open(image_path)

    print("Analyzing invoice structure via Gemini Vision API...")
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            img, 
            "Extract all fields. Capture the full supplier address, locate the 6-digit pincode for the pincode field, and extract the summary total amounts for CGST, SGST, Hamali, and Grand Total exactly as written."
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TallyInvoiceSchema,
            temperature=0.0  # Set to 0.0 for maximum accuracy in financial reporting
        ),
    )
    
    extracted_data = json.loads(response.text)
    compiled_rows = []
    
    # Process items using enumeration to know which row is the first one
    for index, item in enumerate(extracted_data.get("line_items", [])):
        
        # Header/footer totals should ONLY appear on the first row of the invoice block to match Accounting Invoice requirements
        is_first_row = (index == 0)
        
        row_entry = {
            "Voucher Type Name": "Purchase",
            "Voucher class": "GST",
            "Voucher Date": extracted_data.get("invoice_date"),
            "Voucher Number": extracted_data.get("invoice_no"),
            "Ledger Name": extracted_data.get("party_ledger_name"),
            " Group Name": "Sundry Creditors",
            "Buyer/Supplier - Address": extracted_data.get("supplier_address") if is_first_row else "",
            "Buyer/Supplier - State": "Andhra Pradesh",
            "Place of supplier": "Andhra Pradesh",
            "Buyer/Supplier - Pincode": extracted_data.get("supplier_pincode") if is_first_row else "",
            "Country": "India" if is_first_row else "",
            "Mobile Number": "",
            "Registration type": "Regular" if is_first_row else "",
            "GSTIN": extracted_data.get("gstin") if is_first_row else "",
            
            # Grand total ledger amount only goes on row 1 to prevent duplication
            "Ledger Amount": extracted_data.get("grand_total") if is_first_row else "",
            "Ledger Amount Dr/Cr": "cr" if is_first_row else "",
            
            # Item Level Allocations (Always populated on every item row)
            "Item Name": item.get("description_of_goods"),
            "Alias": "",
            "Depcription of Item ": "",
            "HSN": item.get("hsn_sac"),
            "Billed Quantity": item.get("quantity"),
            "Units": "PCS",
            "GST Rate": item.get("gst_rate"),
            "Item Rate per": item.get("rate"),
            "Discount": "",
            "Item Amount": item.get("amount"),
            
            # Absolute summary values allocated strictly on Row 1 to align with your verified ledger configuration
            "Hamali Charges@5%": extracted_data.get("hamali_charges") if (is_first_row and extracted_data.get("hamali_charges", 0) > 0) else "",
            "CGST ": extracted_data.get("cgst_amount") if is_first_row else "",
            "SGST": extracted_data.get("sgst_amount") if is_first_row else "",
            "IGST": "",
            "Round off": extracted_data.get("round_off") if is_first_row else "",
            "Round Off Dr/Cr": "dr" if is_first_row else "",
            "Change Mode ": "Accounting Invoice"
        }
        compiled_rows.append(row_entry)
        
    df_tally = pd.DataFrame(compiled_rows)
    
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        df_tally.to_excel(writer, sheet_name='Accounting Voucher', index=False)
        
    print(f"Success! Updated template file generated cleanly at: {output_excel_path}")

if __name__ == "__main__":
    os.environ["GEMINI_API_KEY"] = "AIzaSyAoqpWm2IeUAmxCQF2WGE4yv-qwvtpYfTo"
    
    TARGET_FOLDER = "Tally_Uploads"
    if not os.path.exists(TARGET_FOLDER):
        os.makedirs(TARGET_FOLDER)
        print(f"Created new directory: {TARGET_FOLDER}")
        
    input_image = "data/invoiceSample.jpeg" 
    output_excel = os.path.join(TARGET_FOLDER, "Purchase_Format_Invoice_Fixed-v1.xlsx")
    
    # Run processing function
    extract_and_convert_to_exact_tally_format(input_image, output_excel)