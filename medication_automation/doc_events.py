import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, time_diff_in_hours, add_days, now_datetime, get_time, add_to_date
from healthcare.healthcare.doctype.patient_encounter.patient_encounter import get_prescription_dates

@frappe.whitelist()
def create_inpatient_medication_order(encounter, start_time=None):
    """Create Inpatient Medication Order from Patient Encounter"""
    encounter_doc = frappe.get_doc("Patient Encounter", encounter)
    
    if not encounter_doc.drug_prescription:
        frappe.throw(_("No drugs prescribed in this encounter"))
    
    # Create Inpatient Medication Order
    medication_order = frappe.new_doc("Inpatient Medication Order")
    medication_order.patient = encounter_doc.patient
    medication_order.patient_encounter = encounter_doc.name
    medication_order.company = encounter_doc.company
    medication_order.start_date = encounter_doc.encounter_date
    
    # Get inpatient record and service unit
    inpatient_record = frappe.db.get_value("Patient", encounter_doc.patient, "inpatient_record")
    service_unit = get_patient_service_unit(inpatient_record)
    
    for drug in encounter_doc.drug_prescription:
        add_order_entries(medication_order, drug, start_time, service_unit)
    
    medication_order.insert()
    if encounter_doc.docstatus == 1:  # Only submit if encounter is submitted
        medication_order.submit()
    
    frappe.msgprint(_("Medication Order {0} created successfully").format(medication_order.name))
    return medication_order.name

def add_order_entries(medication_order, drug, start_time=None, service_unit=None):
    """Add medication order entries from prescription"""
    if not drug.get('drug_code'):
        return
        
    # Get the dosage document for strength and timing
    dosage = None
    if drug.dosage:
        try:
            dosage = frappe.get_doc("Prescription Dosage", drug.dosage)
        except frappe.DoesNotExistError:
            frappe.msgprint(f"Dosage {drug.dosage} not found. Using default scheduling.")
    
    # Get all dates for the prescription period
    dates = []
    if drug.period:
        try:
            dates = get_prescription_dates(drug.period, medication_order.start_date)
            if dates:
                medication_order.end_date = dates[-1]
        except Exception as e:
            frappe.msgprint(f"Error calculating dates for period {drug.period}: {str(e)}")
            # Fallback to single day if period calculation fails
            dates = [medication_order.start_date]
    else:
        # If no period specified, default to single day
        dates = [medication_order.start_date]
    
    # Get interval and interval_uom
    interval = drug.get('interval', 1)
    interval_uom = drug.get('interval_uom', 'Day')
    
    # If we have a dosage document with strength entries
    if dosage and dosage.dosage_strength:
        # For each date in the prescription period
        for date in dates:
            # For each dosage timing
            for dose in dosage.dosage_strength:
                # Skip entries based on interval
                if interval_uom == 'Day' and dates.index(date) % interval != 0:
                    continue
                    
                # Use provided start_time or dosage's strength_time
                time_to_use = start_time if start_time else dose.strength_time
                    
                medication_order.append("medication_orders", {
                    "drug": drug.drug_code,
                    "drug_name": drug.drug_name,
                    "dosage": dose.strength,
                    "period": drug.period,
                    "dosage_form": drug.dosage_form,
                    "date": date,
                    "time": time_to_use,
                    "comment": drug.comment,
                    "instructions": drug.get('instructions') or drug.comment,
                    "service_unit": service_unit
                })
    else:
        # Default timings if no dosage schedule
        base_time = get_time(start_time) if start_time else get_time('09:00:00')
        hours_interval = 24 // 4  # QID spacing
        default_times = []
        
        # Calculate times based on start_time if provided
        for i in range(4):
            time = add_to_date(f"2000-01-01 {base_time}", hours=i * hours_interval)
            default_times.append(time.strftime('%H:%M:%S'))
            
        frequency = drug.get('frequency') or 'Once Daily'
        
        # Map frequency to number of times per day
        frequency_map = {
            'Once Daily': 1,    # OD - Once daily
            'Twice Daily': 2,   # BID - Twice daily
            'Thrice Daily': 3,  # TID - Three times daily
            'Four Times Daily': 4,  # QID - Four times daily
            'Once Weekly': 1,   # Once weekly
            'Once Monthly': 1   # Once monthly
        }
        times_per_day = frequency_map.get(frequency, 1)
        
        # For each date in the prescription period
        for date in dates:
            # Skip entries based on interval and interval_uom
            if interval_uom == 'Day' and dates.index(date) % interval != 0:
                continue
            elif interval_uom == 'Week' and dates.index(date) % (interval * 7) != 0:
                continue
            elif interval_uom == 'Month' and dates.index(date) % (interval * 30) != 0:
                continue
                
            # Add entries for each time based on frequency
            for i in range(times_per_day):
                medication_order.append("medication_orders", {
                    "drug": drug.drug_code,
                    "drug_name": drug.drug_name,
                    "dosage": drug.get('dosage') or 1,
                    "period": drug.period,
                    "dosage_form": drug.dosage_form,
                    "date": date,
                    "time": default_times[i],
                    "comment": drug.comment,
                    "instructions": drug.get('instructions') or drug.comment,
                    "service_unit": service_unit
                })

def on_submit_medication_entry(doc, method):
    """Handle stock entry and sales invoice creation on medication entry submission"""
    try:
        # First create stock entry for consumables
        if doc.custom_consumables:
            create_consumables_stock_entry(doc)
        
        # Then create sales invoice
        create_sales_invoice(doc)
    except Exception as e:
        frappe.log_error(f"Error processing medication entry {doc.name}: {str(e)}")
        frappe.throw(_("Error processing medication entry. Please check error logs."))

    # Mark medication orders as completed when the entry is submitted
    for medication in doc.medication_orders:
        if medication.against_imoe:  # Check if this is linked to an order entry
            frappe.db.set_value("Inpatient Medication Order Entry", 
                              medication.against_imoe, 
                              "is_completed", 1)
    frappe.db.commit()

def create_consumables_stock_entry(doc):
    """Create stock entry for consumables"""
    if not doc.custom_consumables or not doc.warehouse:
        return
        
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = "Material Issue"
    stock_entry.company = doc.company
    stock_entry.posting_date = doc.posting_date
    stock_entry.from_warehouse = doc.warehouse
    
    for item in doc.custom_consumables:
        stock_entry.append("items", {
            "item_code": item.item,
            "qty": item.qty,
            "uom": item.uom,
            "s_warehouse": doc.warehouse,
            "basic_rate": item.rate if item.billable else 0,
            "allow_zero_valuation_rate": not item.billable
        })
    
    stock_entry.insert()
    stock_entry.submit()
    
    # Try to link stock entry to medication entry, handle case where column doesn't exist
    try:
        frappe.db.set_value("Inpatient Medication Entry", doc.name, 
                           "custom_consumables_stock_entry", stock_entry.name)
    except Exception as e:
        frappe.log_error(f"Could not set stock entry reference for {doc.name}: {str(e)}")
        # Continue processing as this is not a critical error
        pass

def create_sales_invoice(doc):
    """Create sales invoice for medications and billable consumables"""
    # Get the first medication order's patient
    patient = doc.medication_orders[0].patient if doc.medication_orders else None
    if not patient:
        frappe.throw(_("No patient found in medication orders"))
        
    # Get customer from patient
    customer = frappe.db.get_value("Patient", patient, "customer")
    if not customer:
        frappe.throw(_("No customer linked to patient {0}").format(patient))

    invoice = frappe.new_doc("Sales Invoice")
    invoice.patient = patient
    invoice.customer = customer
    invoice.company = doc.company
    invoice.posting_date = doc.posting_date
    invoice.due_date = doc.posting_date
    
    # Add medication items
    for medication in doc.medication_orders:
        add_medication_item(invoice, medication)
    
    # Add consumable items
    for consumable in doc.custom_consumables:
        if consumable.billable:
            add_consumable_item(invoice, consumable, doc.warehouse)
    
    invoice.set_missing_values()
    invoice.set_taxes()
    
    invoice.insert()
    invoice.submit()
    
    # Link invoice to medication entry
    frappe.db.set_value("Inpatient Medication Entry", doc.name, 
                       "custom_sales_invoice", invoice.name)

def add_medication_item(invoice, medication):
    """Add medication item to sales invoice"""
    item_code = medication.drug_code
    if not frappe.db.exists("Item", item_code):
        frappe.throw(_("Item {0} not found").format(item_code))
        
    income_account = frappe.db.get_value("Item Default", 
        {"parent": item_code, "company": invoice.company},
        "income_account"
    )
    
    # Get warehouse from parent document
    warehouse = frappe.db.get_value("Inpatient Medication Entry", medication.parent, "warehouse")
    
    invoice.append("items", {
        "item_code": item_code,
        "qty": medication.dosage or 1,
        "rate": frappe.db.get_value("Item", item_code, "standard_rate") or 0,
        "warehouse": warehouse,
        "income_account": income_account,
        "description": f"{medication.drug_name} - {medication.dosage} units"
    })

def add_consumable_item(invoice, consumable, warehouse):
    """Add consumable item to sales invoice"""
    income_account = frappe.db.get_value("Item Default", 
        {"parent": consumable.item, "company": invoice.company},
        "income_account"
    )
    
    invoice.append("items", {
        "item_code": consumable.item,
        "qty": consumable.qty,
        "uom": consumable.uom,
        "warehouse": warehouse,
        "income_account": income_account,
        "rate": consumable.rate,
        "amount": consumable.amount
    })

def get_service_unit_rate(service_unit):
    """Get the billing rate for a service unit"""
    service_unit_type = frappe.db.get_value("Healthcare Service Unit", service_unit, "service_unit_type")
    if service_unit_type:
        is_billable = frappe.db.get_value("Healthcare Service Unit Type", service_unit_type, "is_billable")
        if is_billable:
            item = frappe.db.get_value("Healthcare Service Unit Type", service_unit_type, "item")
            if item:
                return frappe.db.get_value("Item", item, "standard_rate") or 0
    return 0

def calculate_service_unit_hours(medication_entry):
    """Calculate the hours for service unit billing"""
    service_units = {}
    for medication in medication_entry.medication_orders:
        if medication.service_unit:
            if medication.service_unit not in service_units:
                service_units[medication.service_unit] = {
                    'hours': 0,
                    'rate': get_service_unit_rate(medication.service_unit)
                }
            # Add 1 hour for each medication administration
            service_units[medication.service_unit]['hours'] += 1
    return service_units

def get_patient_service_unit(inpatient_record):
    """Get current service unit for patient"""
    if not inpatient_record:
        return None
        
    service_unit = frappe.db.get_value("Inpatient Record", inpatient_record, "service_unit")
    if not service_unit:
        # Try to get from latest occupancy
        occupancy = frappe.get_all(
            "Inpatient Occupancy",
            filters={"inpatient_record": inpatient_record, "left": 0},
            fields=["service_unit"],
            order_by="creation desc",
            limit=1
        )
        if occupancy:
            service_unit = occupancy[0].service_unit
            
    return service_unit 