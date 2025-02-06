import frappe
from frappe import _
from frappe.utils import flt, cint
from erpnext.stock.get_item_details import get_item_details

@frappe.whitelist()
def fetch_medication_orders(posting_date, warehouse=None):
    """
    Fetch medication orders for a specific date, focusing on drug and dosage
    Args:
        posting_date: Date to fetch orders for
        warehouse: Source warehouse (optional)
    Returns:
        List of dictionaries containing medication requirements
    """
    try:
        if not warehouse:
            settings = frappe.get_single("Medication Automation Settings")
            warehouse = settings.default_pharmacy_warehouse
            
        if not warehouse:
            frappe.throw(_("Please set a warehouse or configure default pharmacy warehouse in Medication Automation Settings"))

        # Get all active inpatient medication orders
        orders = frappe.get_all(
            "Inpatient Medication Order",
            filters={
                "docstatus": 1,  # Submitted
                "custom_treatment_status": "Active"
            },
            fields=["name", "patient"]
        )

        if not orders:
            frappe.msgprint(_("No active medication orders found"))
            return []

        # Dictionary to store aggregated medication requirements
        medications_needed = {}
        
        for order in orders:
            # Get medications scheduled for the selected date
            medications = frappe.get_all(
                "Inpatient Medication Order Entry",
                filters=[
                    ["parent", "=", order.name],
                    ["date", "=", posting_date],
                    ["is_completed", "=", 0]  # Only fetch incomplete orders
                ],
                fields=["drug", "drug_name", "dosage", "is_completed"]
            )

            # Aggregate medications by drug
            for med in medications:
                if med.drug not in medications_needed:
                    # Get Item details including UOM
                    stock_uom = frappe.db.get_value("Item", med.drug, "stock_uom")
                    
                    medications_needed[med.drug] = {
                        "drug": med.drug,
                        "drug_name": med.drug_name,
                        "total_qty": 0,
                        "pending_orders": 0,
                        "uom": stock_uom,
                        "stock_uom": stock_uom,
                        "conversion_factor": 1.0
                    }
                medications_needed[med.drug]["total_qty"] += med.dosage
                medications_needed[med.drug]["pending_orders"] += 1

        # Convert dictionary to list and add verification info
        result = []
        for drug, details in medications_needed.items():
            # Get total orders vs completed orders
            total_orders = frappe.db.count(
                "Inpatient Medication Order Entry",
                filters={
                    "drug": drug,
                    "date": posting_date
                }
            )
            
            completed_orders = frappe.db.count(
                "Inpatient Medication Order Entry",
                filters={
                    "drug": drug,
                    "date": posting_date,
                    "is_completed": 1
                }
            )
            
            result.append({
                "drug": drug,
                "drug_name": details["drug_name"],
                "total_qty": details["total_qty"],
                "pending_orders": details["pending_orders"],
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "completion_status": f"{completed_orders}/{total_orders} orders completed",
                "uom": details["uom"],
                "stock_uom": details["stock_uom"],
                "conversion_factor": details["conversion_factor"]
            })
            
        if not result:
            frappe.msgprint(_("No pending medication orders found for the selected date"))
            
        return result

    except Exception as e:
        frappe.log_error(f"Error fetching medication orders: {str(e)}")
        frappe.throw(_("Error fetching medication orders. Please check error logs."))

@frappe.whitelist()
def fetch_item_details(item_code, company, from_warehouse=None, to_warehouse=None):
    """Fetch complete item details for stock entry"""
    if not item_code or not company:
        return {}
        
    args = {
        "item_code": item_code,
        "company": company,
        "doctype": "Stock Entry",
        "is_stock_entry": 1,
        "warehouse": from_warehouse,
        "transfer_qty": 0,
        "conversion_factor": 1.0
    }
    
    item_details = get_item_details(args)
    
    # Get batch details if item has batch
    batch_details = {}
    if item_details.get("has_batch_no"):
        # Get latest batch with stock
        batch = frappe.get_all(
            "Batch",
            filters={
                "item": item_code,
                "disabled": 0
            },
            fields=["name", "expiry_date"],
            order_by="creation desc",
            limit=1
        )
        if batch:
            batch_details = {
                "batch_no": batch[0].name,
                "expiry_date": batch[0].expiry_date
            }
    
    # Get default accounts
    item_defaults = frappe.get_all(
        "Item Default",
        filters={
            "parent": item_code,
            "company": company
        },
        fields=["expense_account", "cost_center"]
    )
    
    # Combine all details
    result = {
        "item_group": item_details.get("item_group"),
        "description": item_details.get("description"),
        "stock_uom": item_details.get("stock_uom"),
        "conversion_factor": item_details.get("conversion_factor", 1.0),
        "valuation_rate": item_details.get("valuation_rate", 0),
        "has_batch_no": item_details.get("has_batch_no", 0),
        "has_serial_no": item_details.get("has_serial_no", 0),
        "expense_account": item_defaults[0].expense_account if item_defaults else None,
        "cost_center": item_defaults[0].cost_center if item_defaults else None,
    }
    
    # Add batch details if available
    if batch_details:
        result.update(batch_details)
    
    return result 