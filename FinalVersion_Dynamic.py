import os
import json
import re
import pandas as pd
from PIL import Image
from pydantic import BaseModel, Field
from typing import List, Optional
from google import genai
from google.genai import types

# =====================================================================
# 1. FIXED DATA SCHEMA WITH SUPPLIER ADDRESS, PINCODE & MOBILE
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
    supplier_mobile: str = Field(default="", description="Extract any contact mobile number, phone number, or telephone digits listed for the supplier")
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
def extract_and_convert_to_exact_tally_format(image_path: str, target_folder: str):
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("Please set your GEMINI_API_KEY environment variable.")
    
    client = genai.Client()
    img = Image.open(image_path)

    print(f"Analyzing invoice structure via Gemini Vision API for: {image_path}...")
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            img, 
            "Extract all fields. Capture the full supplier address, locate the 6-digit pincode, pull any contact/mobile number listed, and extract the summary total amounts for CGST, SGST, Hamali, and Grand Total exactly as written."
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TallyInvoiceSchema,
            temperature=0.0  # Set to 0.0 for maximum accuracy in financial reporting
        ),
    )
    
    extracted_data = json.loads(response.text)
    compiled_rows = []
    
    line_items = extracted_data.get("line_items", [])
    total_items_count = len(line_items)
    
    # Extract structural totals directly from the validated invoice summary
    invoice_total_taxable = extracted_data.get("total_taxable_value", 0.0)
    invoice_total_cgst = extracted_data.get("cgst_amount", 0.0)
    invoice_total_sgst = extracted_data.get("sgst_amount", 0.0)
    
    # If total taxable value extracted is zero, fallback to summing up the items to prevent division by zero
    if invoice_total_taxable == 0.0:
        invoice_total_taxable = sum(item.get("amount", 0.0) for item in line_items)

    # Accumulators to perform clean decimal discrepancy adjustments on the final row
    calculated_cgst_so_far = 0.0
    calculated_sgst_so_far = 0.0
    
    # Process items using enumeration to know which row is the first/last one
    for index, item in enumerate(line_items):
        item_amount = item.get("amount", 0.0)
        is_first_row = (index == 0)
        is_last_row = (index == total_items_count - 1)
        
        # --- PROPORTIONAL TAX DISTRIBUTION WITH COMPONENT RETENTION ---
        if invoice_total_taxable > 0:
            # Determine this specific item row's exact percentage share of the invoice
            item_share_ratio = item_amount / invoice_total_taxable
            
            if not is_last_row:
                # Distribute tax proportionally down to 2 decimal places
                row_cgst = round(invoice_total_cgst * item_share_ratio, 2)
                row_sgst = round(invoice_total_sgst * item_share_ratio, 2)
                
                calculated_cgst_so_far += row_cgst
                calculated_sgst_so_far += row_sgst
            else:
                # The final row absorbs any residual rounding decimals to match the absolute summary perfectly
                row_cgst = round(invoice_total_cgst - calculated_cgst_so_far, 2)
                row_sgst = round(invoice_total_sgst - calculated_sgst_so_far, 2)
        else:
            row_cgst = 0.0
            row_sgst = 0.0

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
            "Mobile Number": subgroup_val if (subgroup_val := extracted_data.get("supplier_mobile")) and is_first_row else "",
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
            "CGST ": row_cgst,
            "SGST": row_sgst,
            "IGST": "",
            "Round off": extracted_data.get("round_off") if is_first_row else "",
            "Round Off Dr/Cr": "dr" if is_first_row else "",
            "Change Mode ": "Accounting Invoice"
        }
        compiled_rows.append(row_entry)
        
    df_tally = pd.DataFrame(compiled_rows)
    
    # --- DYNAMIC FILENAME GENERATION ---
    safe_invoice_no = re.sub(r'[\\/*?:"<>|]', '_', str(extracted_data.get("invoice_no", "UNKNOWN")))
    safe_ledger_name = re.sub(r'[\\/*?:"<>| ]', '_', str(extracted_data.get("party_ledger_name", "PARTY")))
    
    file_name = f"{safe_ledger_name}_{safe_invoice_no}.xlsx"
    output_excel_path = os.path.join(target_folder, file_name)
    
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        df_tally.to_excel(writer, sheet_name='Accounting Voucher', index=False)
        
    print(f"Success! Updated template file generated cleanly at: {output_excel_path}")
    return output_excel_path

# =====================================================================
# 3. RUNTIME EXECUTION
# =====================================================================
if __name__ == "__main__":
    os.environ["GEMINI_API_KEY"] = "AIzaSyAoqpWm2IeUAmxCQF2WGE4yv-qwvtpYfTo"
    
    TARGET_FOLDER = "Tally_Uploads"
    if not os.path.exists(TARGET_FOLDER):
        os.makedirs(TARGET_FOLDER)
        print(f"Created new directory: {TARGET_FOLDER}")
        
    input_image = "data/invoiceSample.jpeg" 
    
    generated_path = extract_and_convert_to_exact_tally_format(input_image, TARGET_FOLDER)
    print(f"Final accounting file produced: {generated_path}")