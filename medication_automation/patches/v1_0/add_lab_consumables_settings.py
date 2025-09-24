import frappe

def execute():
    """Add default values for laboratory and radiology warehouses in Medication Automation Settings"""
    try:
        # Check if settings doc exists
        if not frappe.db.exists("Medication Automation Settings"):
            # Create settings doc if it doesn't exist
            doc = frappe.new_doc("Medication Automation Settings")
            # Don't set any defaults for warehouses
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.msgprint("Created Medication Automation Settings.")
    except Exception as e:
        frappe.log_error("Error in lab consumables patch", "Lab Consumables Patch Error") 