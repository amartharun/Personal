import os
import json
from PIL import Image
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Optional
from google import genai
from google.genai import types

# =====================================================================
# 1. DEFINE STRUCUTRED TALLY-COMPLIANT DATA SCHEMA
# =====================================================================
class InvoiceItem(BaseModel):
    sl_no: Optional[int] = Field(description="Serial number of the item row")
    description_of_goods: str = Field(description="The name or description of the product/stock item")
    hsn_sac: str = Field(description="HSN or SAC code")
    gst_rate: str = Field(description="GST percentage rate applied (e.g., 5%)")
    quantity: int = Field(description="Quantity unit count")
    rate: float = Field(description="Rate per piece/unit excluding tax")
    amount: float = Field(description="Total item value before tax (Quantity * Rate)")

class TallyInvoiceSchema(BaseModel):
    invoice_no: str = Field(description="Unique Tax Invoice Number")
    invoice_date: str = Field(description="Date of invoice format DD-Mon-YY or DD-MM-YYYY")
    party_ledger_name: str = Field(description="The seller/supplier business name for Tally ledger mapping")
    consignee_name: str = Field(description="The buyer/consignee name")
    
    # Financial breakdowns needed for Tally Ledger entries
    total_taxable_value: float = Field(description="Sum total of item amounts before tax")
    hamali_charges: float = Field(default=0.0, description="Any loading, labor, or hamali charges if present")
    cgst_amount: float = Field(description="Total CGST tax amount calculated")
    sgst_amount: float = Field(description="Total SGST tax amount calculated")
    igst_amount: float = Field(default=0.0, description="Total IGST tax amount calculated if interstate")
    round_off: float = Field(default=0.0, description="Invoice rounding balance variation amount")
    grand_total: float = Field(description="Final payable net value of invoice")
    
    # Inventory list
    line_items: List[InvoiceItem] = Field(description="List of all stock line items split in rows")

# =====================================================================
# 2. RUN EXTRACTION AND EXCEL GENERATION
# =====================================================================
def extract_and_convert_to_tally_excel(image_path: str, output_excel_path: str):
    # Setup Client (Picks up GEMINI_API_KEY environment variable)
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("Please set your GEMINI_API_KEY environment variable.")
    
    client = genai.Client()
    
    print(f"Loading image target: {image_path}...")
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"Error opening image file: {e}")
        return

    print("Analyzing invoice structure via Gemini API...")
    
    # Structured extraction target via gemini-2.5-flash
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            img, 
            "Extract all financial data and inventory line items precisely from this tax invoice layout according to the requested structural JSON schema."
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TallyInvoiceSchema,
            temperature=0.1 # Lower temperature ensures high deterministic consistency
        ),
    )
    
    # Parse output data payload
    extracted_data = json.loads(response.text)
    
    print("Transforming structural elements into Tally transaction sheets...")
    
    # --- Formulate Sheet 1: Voucher Headers ---
    header_data = {
        "Voucher_Type": ["Purchase"], # Defaults to standard input journal voucher context
        "Invoice_No": [extracted_data.get("invoice_no")],
        "Date": [extracted_data.get("invoice_date")],
        "Party_Ledger": [extracted_data.get("party_ledger_name")],
        "Purchase_Ledger": ["Purchase Accounts"], 
        "Taxable_Value": [extracted_data.get("total_taxable_value")],
        "Hamali_Ledger": ["Hamali Charges" if extracted_data.get("hamali_charges", 0) > 0 else ""],
        "Hamali_Amount": [extracted_data.get("hamali_charges")],
        "CGST_Ledger": ["Input CGST"],
        "CGST_Amount": [extracted_data.get("cgst_amount")],
        "SGST_Ledger": ["Input SGST"],
        "SGST_Amount": [extracted_data.get("sgst_amount")],
        "IGST_Ledger": ["Input IGST"],
        "IGST_Amount": [extracted_data.get("igst_amount")],
        "Round_Off_Ledger": ["Round Off"],
        "Round_Off_Amount": [extracted_data.get("round_off")],
        "Grand_Total": [extracted_data.get("grand_total")]
    }
    df_headers = pd.DataFrame(header_data)
    
    # --- Formulate Sheet 2: Voucher Items (Inventory Allocations) ---
    items_list = []
    for item in extracted_data.get("line_items", []):
        items_list.append({
            "Parent_Invoice_No": extracted_data.get("invoice_no"), # Reference pointer to track headers
            "Stock_Item_Name": item.get("description_of_goods"),
            "HSN_SAC": item.get("hsn_sac"),
            "GST_Rate": item.get("gst_rate"),
            "Quantity": item.get("quantity"),
            "Unit": "PCS",
            "Rate_Per_Unit": item.get("rate"),
            "Item_Amount": item.get("amount")
        })
    df_items = pd.DataFrame(items_list)
    
    # --- Write to Multi-Tab Excel Workbook ---
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        df_headers.to_excel(writer, sheet_name='Voucher_Headers', index=False)
        df_items.to_excel(writer, sheet_name='Voucher_Items', index=False)
        
    print(f"Success! Relational sheets created safely at: {output_excel_path}")

# =====================================================================
# 3. EXECUTION PROCESS
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
    output_excel = os.path.join(TARGET_FOLDER, "Tally_Import_Ready_Invoice.xlsx")
    
    # Run your processing function
    extract_and_convert_to_exact_tally_format(input_image, output_excel)