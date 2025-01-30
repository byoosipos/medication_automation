import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime
from .automation import check_medication_status, get_patient_service_unit
from healthcare.config.serverscript import auto_create_medication_entries

def create_medication_entries():
    """
    Scheduler job to create medication entries
    Checks medication status before creating entries
    """
    # Get active medication orders
    orders = frappe.get_all(
        "Inpatient Medication Order",
        filters={
            "docstatus": 1,  # Submitted
            "status": "Active"
        },
        fields=["name", "patient_encounter", "patient"]
    )
    
    current_datetime = now_datetime()
    
    for order in orders:
        # Check if medication is still active for this encounter
        if not check_medication_status(order.patient_encounter):
            continue
            
        order_doc = frappe.get_doc("Inpatient Medication Order", order.name)
        
        # Get inpatient record and service unit
        inpatient_record = frappe.db.get_value("Patient", order.patient, "inpatient_record")
        service_unit = get_patient_service_unit(inpatient_record)
        
        # Get medication orders due in the next interval
        due_medications = frappe.get_all(
            "Inpatient Medication Order Entry",
            filters={
                "parent": order.name,
                "date": current_datetime.date(),
                "time": ["<=", current_datetime.strftime("%H:%M:%S")],
                "is_completed": 0
            }
        )
        
        for medication in due_medications:
            try:
                create_medication_entry(medication, order_doc, service_unit)
            except Exception as e:
                frappe.log_error(
                    f"Error creating medication entry for order {order.name}, "
                    f"medication {medication.name}: {str(e)}"
                )

def create_medication_entry(medication, order_doc, service_unit=None):
    """Create individual medication entry"""
    medication_doc = frappe.get_doc("Inpatient Medication Order Entry", medication.name)
    
    if medication_doc.is_completed:
        return
        
    entry = frappe.get_doc({
        "doctype": "Inpatient Medication Entry",
        "patient": order_doc.patient,
        "patient_encounter": order_doc.patient_encounter,
        "company": order_doc.company,
        "medication_order": order_doc.name,
        "drug": medication_doc.drug,
        "drug_name": medication_doc.drug_name,
        "dosage": medication_doc.dosage,
        "dosage_form": medication_doc.dosage_form,
        "date": medication_doc.date,
        "time": medication_doc.time,
        "comment": medication_doc.comment,
        "update_stock": 1  # Enable stock update
    })
    
    # Add medication order with service unit
    entry.append("medication_orders", {
        "drug": medication_doc.drug,
        "drug_name": medication_doc.drug_name,
        "dosage": medication_doc.dosage,
        "dosage_form": medication_doc.dosage_form,
        "date": medication_doc.date,
        "time": medication_doc.time,
        "comment": medication_doc.comment,
        "service_unit": service_unit or medication_doc.service_unit,  # Use provided service unit or from medication doc
        "against_imo": order_doc.name,
        "patient": order_doc.patient,
        "patient_name": frappe.db.get_value("Patient", order_doc.patient, "patient_name")
    })
    
    entry.insert()
    entry.submit()
    
    # Mark the medication as completed
    medication_doc.is_completed = 1
    medication_doc.save()

def schedule_medication_entries():
    """
    Scheduler event to create medication entries
    Runs every minute to check for pending orders
    """
    try:
        frappe.logger().debug("Starting medication entry scheduler")
        create_medication_entries()
        frappe.logger().debug("Medication entries created successfully")
    except Exception as e:
        frappe.logger().error(f"Error in medication entry scheduler: {str(e)}")
        frappe.log_error(f"Error in medication entry scheduler: {str(e)}", "Medication Scheduler Error") 