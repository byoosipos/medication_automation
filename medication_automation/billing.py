import frappe
from frappe.utils import date_diff, add_to_date, now_datetime
from .automation import get_item_rate

def create_admission_billing(inpatient_record):
    """
    Create initial billing on admission including:
    1. Room charges for expected stay
    2. Initial care charges for first period
    """
    try:
        doc = frappe.get_doc("Inpatient Record", inpatient_record)
        if not doc.admitted_datetime or not doc.expected_discharge:
            return
            
        # Calculate expected stay duration
        expected_days = date_diff(doc.expected_discharge.date(), doc.admitted_datetime.date())
        if expected_days <= 0:
            return
            
        # Get current service unit details
        current_occupancy = frappe.get_all(
            "Inpatient Occupancy",
            filters={
                "parent": inpatient_record,
                "left": 0
            },
            fields=["service_unit", "name", "check_in"],
            order_by="check_in desc",
            limit=1
        )
        
        if not current_occupancy:
            return
            
        service_unit = current_occupancy[0].service_unit
        service_unit_type = frappe.db.get_value(
            "Healthcare Service Unit",
            service_unit,
            "service_unit_type"
        )
        
        if not service_unit_type:
            return
            
        unit_type_doc = frappe.get_doc("Healthcare Service Unit Type", service_unit_type)
        
        # Create Sales Invoice for admission charges
        invoice = frappe.get_doc({
            "doctype": "Sales Invoice",
            "patient": doc.patient,
            "customer": frappe.db.get_value("Patient", doc.patient, "customer"),
            "company": doc.company,
            "posting_date": doc.admitted_datetime.date(),
            "due_date": doc.admitted_datetime.date(),
            "items": []
        })
        
        # Add room charges
        if unit_type_doc.is_billable and unit_type_doc.item_code:
            room_rate = get_item_rate(unit_type_doc.item_code, doc.company, "Day")
            if room_rate:
                invoice.append("items", {
                    "item_code": unit_type_doc.item_code,
                    "qty": expected_days,
                    "uom": "Day",
                    "rate": room_rate,
                    "reference_dt": "Inpatient Record",
                    "reference_dn": inpatient_record,
                    "description": f"Room Charges (Advance) for {expected_days} days from {doc.admitted_datetime.date()}"
                })
                
        # Add initial care charges if configured
        care_settings = frappe.get_doc("Healthcare Settings")
        if care_settings.inpatient_care_item:
            care_rate = get_item_rate(care_settings.inpatient_care_item, doc.company, "Day")
            if care_rate:
                # Bill for first period based on frequency
                invoice.append("items", {
                    "item_code": care_settings.inpatient_care_item,
                    "qty": 1,
                    "uom": "Day",
                    "rate": care_rate,
                    "reference_dt": "Inpatient Record",
                    "reference_dn": inpatient_record,
                    "description": f"Initial Care Charges for {care_settings.care_billing_frequency} hours from {doc.admitted_datetime}"
                })
        
        if invoice.items:
            invoice.insert()
            invoice.submit()
            
            # Update inpatient record
            doc.db_set('admission_invoice', invoice.name)
            
            # Schedule next care billing
            schedule_next_care_billing(doc)
            
        return invoice.name if invoice.items else None
        
    except Exception as e:
        frappe.log_error(
            f"Error creating admission billing for {inpatient_record}: {str(e)}",
            "Admission Billing Error"
        )
        return None

def schedule_next_care_billing(inpatient_record):
    """Schedule next care charge billing"""
    if isinstance(inpatient_record, str):
        inpatient_record = frappe.get_doc("Inpatient Record", inpatient_record)
        
    care_settings = frappe.get_doc("Healthcare Settings")
    care_billing_frequency = care_settings.care_billing_frequency or 24
    
    # If this is first billing, start from admission
    if not inpatient_record.next_care_billing:
        next_billing = add_to_date(
            inpatient_record.admitted_datetime,
            hours=care_billing_frequency
        )
    else:
        # For subsequent billings, start from last scheduled time
        next_billing = add_to_date(
            inpatient_record.next_care_billing,
            hours=care_billing_frequency
        )
    
    # Store next billing datetime in inpatient record
    inpatient_record.db_set('next_care_billing', next_billing)

def process_care_billing():
    """
    Process recurring care charges for admitted patients
    Should be run by a scheduled job every hour
    """
    current_time = now_datetime()
    
    # Find inpatient records due for care billing
    records = frappe.get_all(
        "Inpatient Record",
        filters={
            "status": "Admitted",
            "next_care_billing": ["<=", current_time]
        },
        fields=["name", "patient", "company", "next_care_billing"]
    )
    
    care_settings = frappe.get_doc("Healthcare Settings")
    if not care_settings.inpatient_care_item:
        return
        
    for record in records:
        try:
            care_rate = get_item_rate(care_settings.inpatient_care_item, record.company, "Day")
            if not care_rate:
                continue
                
            # Create care charges invoice
            invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "patient": record.patient,
                "customer": frappe.db.get_value("Patient", record.patient, "customer"),
                "company": record.company,
                "posting_date": current_time.date(),
                "items": [{
                    "item_code": care_settings.inpatient_care_item,
                    "qty": 1,
                    "uom": "Day",
                    "rate": care_rate,
                    "reference_dt": "Inpatient Record",
                    "reference_dn": record.name,
                    "description": f"Care Charges for period starting {record.next_care_billing}"
                }]
            })
            
            invoice.insert()
            invoice.submit()
            
            # Update inpatient record
            frappe.get_doc("Inpatient Record", record.name).db_set('last_care_invoice', invoice.name)
            
            # Schedule next billing
            schedule_next_care_billing(record.name)
            
        except Exception as e:
            frappe.log_error(
                f"Error processing care billing for {record.name}: {str(e)}",
                "Care Billing Error"
            )
            continue 