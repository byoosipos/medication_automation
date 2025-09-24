import frappe
from frappe import _

def validate_consultation_charge(doc, method=None):
    """
    Bypass consultation charge validation for inpatients
    """
    if doc.inpatient_record:
        # If patient is admitted, no need for consultation charge
        doc.consultation_charge = None
        return
        
    # For outpatients, validate consultation charge on save
    if not doc.consultation_charge:
        frappe.throw(_("Consultation Charge is mandatory for outpatient encounters"))

def validate_vital_signs(doc, method=None):
    """
    Remove vital signs requirement for inpatients - they can record vitals anytime
    """
    if doc.inpatient_record:
        # For inpatients, vital signs can be recorded anytime
        return
        
    # For outpatients, check if vital signs exist
    if not doc.get("custom_vital_items") and not doc.get("custom_vitals_id"):
        frappe.throw(_("Vital Signs are mandatory for outpatient encounters"))
