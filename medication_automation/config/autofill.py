import frappe
from frappe import _

@frappe.whitelist()
def get_current_practitioner():
    """Get the healthcare practitioner linked to the logged-in user"""
    user = frappe.session.user
    if not user or user == "Administrator" or user == "Guest":
        return None
        
    # Check if the current user is linked to a Healthcare Practitioner
    practitioner = frappe.db.get_value(
        "Healthcare Practitioner", {"user_id": user}, 
        ["name", "practitioner_name"], 
        as_dict=True
    )
    
    return practitioner

def set_missing_values(doc, method):
    """Set missing values in the Patient Encounter document before save"""
    if not doc.is_new():
        return
        
    # Only autofill practitioner if it's not already set
    if not doc.practitioner:
        practitioner = get_current_practitioner()
        if practitioner:
            doc.practitioner = practitioner.name
            # Also set practitioner name if available
            if hasattr(practitioner, 'practitioner_name') and practitioner.practitioner_name:
                doc.practitioner_name = practitioner.practitioner_name
            
            # Fetch department if not set
            if not doc.medical_department:
                department = frappe.db.get_value(
                    "Healthcare Practitioner", doc.practitioner, "department"
                )
                if department:
                    doc.medical_department = department
