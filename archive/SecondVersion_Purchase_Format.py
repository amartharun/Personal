import os
import json
import pandas as pd
from PIL import Image
from pydantic import BaseModel, Field
from typing import List, Optional
from google import genai
from google.genai import types

# =====================================================================
# 1. STRUCTURAL DATA SCHEMA (MATCHING YOUR TARGET LAYOUT)
# =====================================================================
class InvoiceItem(BaseModel):
    description_of_goods: str = Field(description="The name or description of the stock item")
    hsn_sac: str = Field(description="HSN or SAC code")
    gst_rate: str = Field(description="GST percentage rate applied (e.g., 5%)")
    quantity: int = Field(description="Quantity unit count")
    rate: float = Field(description="Rate per piece/unit excluding tax")
    amount: float = Field(description="Total item value before tax (Quantity * Rate)")

class TallyInvoiceSchema(BaseModel):
    invoice_no: str = Field(description="Unique Tax Invoice Number (e.g., E/SUR-10109)")
    invoice_date: str = Field(description="Date of invoice converted to YYYY-MM-DD format")
    party_ledger_name: str = Field(description="The seller/supplier business name (e.g., KISHORE FABRICS PVT LTD)")
    gstin: str = Field(description="GSTIN of the supplier/seller")
    
    # Financial summary values
    total_taxable_value: float = Field(description="Sum total of item amounts before tax")
    hamali_charges: float = Field(default=0.0, description="Any loading, labor, or hamali charges if present")
    cgst_amount: float = Field(description="Total CGST tax amount calculated")
    sgst_amount: float = Field(description="Total SGST tax amount calculated")
    round_off: float = Field(default=0.0, description="Invoice rounding balance variation amount")
    grand_total: float = Field(description="Final net total payable value of invoice")
    
    # Item mapping arrays
    line_items: List[InvoiceItem] = Field(description="List of all stock line items split in rows")

# =====================================================================
# 2. RUN EXTRACTION AND MATRIX MAPPING
# =====================================================================
def extract_and_convert_to_exact_tally_format(image_path: str, output_excel_path: str):
    # Setup Client (Picks up GEMINI_API_KEY environment variable or code override)
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("Please set your GEMINI_API_KEY environment variable or override it directly.")
    
    client = genai.Client()
    
    print(f"Loading image target: {image_path}...")
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"Error opening image file: {e}")
        return

    print("Analyzing invoice structure via Gemini Vision API...")
    
    # Requesting structure with explicit prompt instructions
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            img, 
            "Extract all financial values and convert the Invoice Date strictly into YYYY-MM-DD format based on the requested JSON schema."
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TallyInvoiceSchema,
            temperature=0.1 
        ),
    )
    
    extracted_data = json.loads(response.text)
    print("Mapping extracted fields to match your exact Tally template headers...")
    
    # Compile multi-row flat file structures matching your exact columns
    compiled_rows = []
    
    for item in extracted_data.get("line_items", []):
        row_entry = {
            "Voucher Type Name": "Purchase",
            "Voucher class": "GST",
            "Voucher Date": extracted_data.get("invoice_date"),
            "Voucher Number": extracted_data.get("invoice_no"),
            "Ledger Name": extracted_data.get("party_ledger_name"),
            " Group Name": "Sundry Creditors",
            "Buyer/Supplier - Address": "",
            "Buyer/Supplier - State": "Andhra Pradesh",
            "Place of supplier": "Andhra Pradesh",
            "Buyer/Supplier - Pincode": "",
            "Country": "",
            "Mobile Number": "",
            "Registration type": "",
            "GSTIN": extracted_data.get("gstin"),
            "Ledger Amount": extracted_data.get("grand_total"),
            "Ledger Amount Dr/Cr": "cr",
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
            "Hamali Charges@5%": extracted_data.get("hamali_charges") if extracted_data.get("hamali_charges", 0) > 0 else "",
            "CGST ": extracted_data.get("cgst_amount"),
            "SGST": extracted_data.get("sgst_amount"),
            "IGST": "",
            "Round off": extracted_data.get("round_off"),
            "Round Off Dr/Cr": "",
            "Change Mode ": "Accounting Invoice"
        }
        compiled_rows.append(row_entry)
        
    # Convert matrix to DataFrame
    df_tally = pd.DataFrame(compiled_rows)
    
    # Write cleanly to single-sheet target mapping destination
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        df_tally.to_excel(writer, sheet_name='Accounting Voucher', index=False)
        
    print(f"Success! Exact template file generated safely at: {output_excel_path}")

# =====================================================================
# 3. DIRECT RUN EXECUTION
# =====================================================================
if __name__ == "__main__":
    # If not using environment variables, paste your API key inside the string below:
    os.environ["GEMINI_API_KEY"] = "AIzaSyAoqpWm2IeUAmxCQF2WGE4yv-qwvtpYfTo"
    
    # 1. Define your target output folder name
    TARGET_FOLDER = "Tally_Uploads"
    
    # 2. Check if the folder exists; if not, create it automatically
    if not os.path.exists(TARGET_FOLDER):
        os.makedirs(TARGET_FOLDER)
        print(f"Created new directory: {TARGET_FOLDER}")
        
    input_image = "data/invoiceSample.jpeg" 
    
    # 3. Combine folder name and file name for the final path
    output_excel = os.path.join(TARGET_FOLDER, "Purchase_Format_Invoice.xlsx")
    
    # Run your processing function
    extract_and_convert_to_exact_tally_format(input_image, output_excel)