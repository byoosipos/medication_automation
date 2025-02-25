import frappe
from frappe import _

@frappe.whitelist()
def get_encounter_details(doc, method=None):
    """Implementation of the missing get_encounter_details method for Patient Encounter"""
    # We can safely return basic encounter details
    return {
        "patient": doc.patient,
        "patient_name": doc.patient_name,
        "practitioner": getattr(doc, "practitioner", None),
        "practitioner_name": getattr(doc, "practitioner_name", None),
        "encounter_date": doc.encounter_date,
        "encounter_time": doc.encounter_time,
        "status": doc.status,
        # Add other fields that might be expected
    } 