import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, add_to_date
from .automation import check_medication_status, get_patient_service_unit

def create_medication_entries():
    """
    Scheduler job to create medication entries
    Runs every minute to create entries for medications due at the exact time
    """
    current_datetime = now_datetime()
    next_minute = add_to_date(current_datetime, minutes=1)
    
    # Get active medication orders
    orders = frappe.get_all(
        "Inpatient Medication Order",
        filters={
            "docstatus": 1,  # Submitted
            "custom_treatment_status": "Active"
        },
        fields=["name", "patient_encounter", "patient"]
    )
    
    for order in orders:
        # Check if medication is still active for this encounter
        if not check_medication_status(order.patient_encounter):
            continue
            
        order_doc = frappe.get_doc("Inpatient Medication Order", order.name)
        
        # Get inpatient record and service unit
        inpatient_record = frappe.db.get_value("Patient", order.patient, "inpatient_record")
        
        if not inpatient_record:
            frappe.log_error(
                f"No active inpatient record found for patient {order.patient}",
                "Medication Entry Creation Error"
            )
            continue
            
        # Verify inpatient record is active
        inpatient_status = frappe.db.get_value("Inpatient Record", inpatient_record, "status")
        if inpatient_status not in ["Admitted", "Discharge Scheduled"]:
            frappe.log_error(
                f"Inpatient record {inpatient_record} for patient {order.patient} is not active (status: {inpatient_status})",
                "Medication Entry Creation Error"
            )
            continue
            
        # Get latest occupancy with service unit
        occupancy = frappe.get_all(
            "Inpatient Occupancy",
            filters={
                "parent": inpatient_record,
                "left": 0
            },
            fields=["service_unit", "name", "check_in"],
            order_by="check_in desc",
            limit=1
        )
        
        if not occupancy:
            frappe.log_error(
                f"No active occupancy found for inpatient record {inpatient_record}",
                "Medication Entry Creation Error"
            )
            continue
            
        service_unit = occupancy[0].service_unit
        
        if not service_unit:
            frappe.log_error(
                f"Could not find service unit for patient {order.patient} with inpatient record {inpatient_record}",
                "Medication Entry Creation Error"
            )
            continue
            
        # Verify service unit exists
        if not frappe.db.exists("Healthcare Service Unit", service_unit):
            frappe.log_error(
                f"Service unit {service_unit} not found in the system for patient {order.patient}",
                "Medication Entry Creation Error"
            )
            continue
            
        # Get medication orders due in the current minute
        due_medications = frappe.get_all(
            "Inpatient Medication Order Entry",
            filters=[
                ["parent", "=", order.name],
                ["date", "=", current_datetime.date()],
                ["time", ">=", current_datetime.strftime("%H:%M:%S")],
                ["time", "<", next_minute.strftime("%H:%M:%S")],
                ["is_completed", "=", 0]
            ],
            fields=["name", "drug", "drug_name", "dosage", "dosage_form", "date", "time"]
        )
        
        if due_medications:
            try:
                # Create a single medication entry for all due medications
                entry = frappe.get_doc({
                    "doctype": "Inpatient Medication Entry",
                    "patient": order.patient,
                    "patient_encounter": order.patient_encounter,
                    "company": order_doc.company,
                    "posting_date": current_datetime.date(),
                    "service_unit": service_unit,
                    "medication_orders": []
                })
                
                for medication in due_medications:
                    entry.append("medication_orders", {
                        "patient": order.patient,
                        "patient_name": frappe.db.get_value("Patient", order.patient, "patient_name"),
                        "inpatient_record": inpatient_record,
                        "service_unit": service_unit,
                        "datetime": get_datetime(f"{medication.date} {medication.time}"),
                        "drug_code": medication.drug,
                        "drug_name": medication.drug_name,
                        "dosage": medication.dosage,
                        "dosage_form": medication.dosage_form,
                        "against_imo": order.name,
                        "against_imoe": medication.name
                    })
                
                frappe.logger().debug(f"Creating medication entry with service unit {service_unit} for patient {order.patient}")
                entry.insert()
                
                # Mark medications as completed only after successful insert
                for medication in due_medications:
                    frappe.db.set_value("Inpatient Medication Order Entry", medication.name, "is_completed", 1)
                frappe.db.commit()
                
            except Exception as e:
                frappe.log_error(
                    f"Error creating medication entry for order {order.name}: {str(e)}",
                    "Medication Entry Creation Error"
                )
                continue

def schedule_medication_entries():
    """
    Scheduler event to create medication entries
    Runs every minute to check for pending orders at exact times
    """
    try:
        frappe.logger().debug("Starting medication entry scheduler")
        create_medication_entries()
        frappe.logger().debug("Medication entries created successfully")
    except Exception as e:
        frappe.logger().error(f"Error in medication entry scheduler: {str(e)}")
        frappe.log_error(f"Error in medication entry scheduler: {str(e)}", "Medication Scheduler Error") 

        