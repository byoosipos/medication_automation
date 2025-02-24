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

def handle_healthcare_billing(doc, patient, items, posting_date=None):
    """Universal handler for healthcare billing with insurance
    Args:
        doc: Source document (Lab Test, Clinical Procedure, etc.)
        patient: Patient document or patient name
        items: List of dictionaries containing billable items with:
            - item_code: Item code
            - item_name: Item name
            - qty: Quantity
            - rate: Rate
            - reference_dt: Reference DocType
            - reference_dn: Reference DocName
            - service_unit: Service Unit (optional)
    """
    if not posting_date:
        posting_date = getdate()

    # Check for active insurance coverage
    active_insurance = frappe.get_all(
        "Insurance Coverage",
        filters={
            "patient": patient,
            "status": "Active",
            "docstatus": 1,
            "coverage_start_date": ["<=", posting_date],
            "coverage_end_date": [">=", posting_date]
        },
        fields=["name"],
        limit=1
    )

    insured_items = []
    non_insured_items = []

    if active_insurance:
        insurance_doc = frappe.get_doc("Insurance Coverage", active_insurance[0].name)
        
        # Check each item for insurance coverage
        for item in items:
            item_group = frappe.db.get_value("Item", item["item_code"], "item_group")
            is_covered = False
            
            # Check if item group is covered by insurance
            for covered_item in insurance_doc.covered_items:
                if covered_item.item_group == item_group:
                    is_covered = True
                    break
            
            if is_covered:
                insured_items.append(item)
            else:
                non_insured_items.append(item)

        # Handle insured items
        if insured_items:
            # Check for existing open claim for the day
            existing_claim = frappe.get_all(
                "Insurance Claim",
                filters={
                    "insurance_coverage": insurance_doc.name,
                    "patient": patient,
                    "claim_date": posting_date,
                    "docstatus": 0  # Draft status
                },
                limit=1
            )

            if existing_claim:
                claim = frappe.get_doc("Insurance Claim", existing_claim[0].name)
            else:
                claim = frappe.new_doc("Insurance Claim")
                claim.insurance_coverage = insurance_doc.name
                claim.patient = patient
                claim.claim_date = posting_date
                claim.company = doc.company

            # Add items to claim
            for item in insured_items:
                claim.append("items", {
                    "item_code": item["item_code"],
                    "item_name": item["item_name"],
                    "amount": item["qty"] * item["rate"],
                    "reference_dt": item["reference_dt"],
                    "reference_dn": item["reference_dn"],
                    "service_unit": item.get("service_unit")
                })

            if not existing_claim:
                claim.insert()
            else:
                claim.save()

    # Handle non-insured items
    if non_insured_items:
        customer = frappe.db.get_value("Patient", patient, "customer")
        if not customer:
            frappe.throw(_("No customer linked to patient {0}").format(patient))

        invoice = frappe.new_doc("Sales Invoice")
        invoice.patient = patient
        invoice.customer = customer
        invoice.company = doc.company
        invoice.posting_date = posting_date
        invoice.due_date = posting_date

        for item in non_insured_items:
            invoice.append("items", {
                "item_code": item["item_code"],
                "item_name": item["item_name"],
                "qty": item["qty"],
                "rate": item["rate"],
                "reference_dt": item["reference_dt"],
                "reference_dn": item["reference_dn"]
            })

        invoice.set_missing_values()
        invoice.set_taxes()
        invoice.insert()
        invoice.submit()

    return {
        "insured_items": len(insured_items),
        "non_insured_items": len(non_insured_items)
    }

def on_submit_medication_entry(doc, method):
    """Handle stock entry and insurance claim/invoice creation on medication entry submission"""
    try:
        # First create stock entry for consumables
        if doc.custom_consumables:
            create_consumables_stock_entry(doc)
        
        # Get patient from first medication order
        patient = doc.medication_orders[0].patient if doc.medication_orders else None
        if not patient:
            frappe.throw(_("No patient found in medication orders"))

        # Prepare billable items list
        billable_items = []

        # Add medication items
        for medication in doc.medication_orders:
            item_code = medication.drug_code
            rate = frappe.db.get_value("Item", item_code, "standard_rate") or 0
            
            billable_items.append({
                "item_code": item_code,
                "item_name": medication.drug_name,
                "qty": medication.dosage or 1,
                "rate": rate,
                "reference_dt": "Inpatient Medication Entry",
                "reference_dn": doc.name,
                "service_unit": medication.service_unit
            })

        # Add consumable items
        for consumable in doc.custom_consumables:
            if consumable.billable:
                billable_items.append({
                    "item_code": consumable.item,
                    "item_name": frappe.db.get_value("Item", consumable.item, "item_name"),
                    "qty": consumable.qty,
                    "rate": consumable.rate,
                    "reference_dt": "Inpatient Medication Entry",
                    "reference_dn": doc.name,
                    "service_unit": doc.service_unit
                })

        # Handle billing with insurance check
        result = handle_healthcare_billing(doc, patient, billable_items, doc.posting_date)

        if result["insured_items"] > 0:
            frappe.db.set_value("Inpatient Medication Entry", doc.name, "custom_insurance_claimed", 1)

    except Exception as e:
        frappe.log_error(f"Error processing medication entry {doc.name}: {str(e)}")
        frappe.throw(_("Error processing medication entry. Please check error logs."))

    # Mark medication orders as completed
    for medication in doc.medication_orders:
        if medication.against_imoe:
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

def validate_sales_invoice(doc, method):
    """Prevent direct invoicing of insured items"""
    if not doc.patient:
        return

    # Check for active insurance coverage
    active_insurance = frappe.get_all(
        "Insurance Coverage",
        filters={
            "patient": doc.patient,
            "status": "Active",
            "docstatus": 1,
            "coverage_start_date": ["<=", doc.posting_date],
            "coverage_end_date": [">=", doc.posting_date]
        },
        fields=["name"],
        limit=1
    )

    if active_insurance:
        insurance_doc = frappe.get_doc("Insurance Coverage", active_insurance[0].name)
        
        # Check each item for insurance coverage
        for item in doc.items:
            item_group = frappe.db.get_value("Item", item.item_code, "item_group")
            
            # Check if item group is covered by insurance
            for covered_item in insurance_doc.covered_items:
                if covered_item.item_group == item_group:
                    frappe.throw(_(
                        "Item {0} belongs to item group {1} which is covered under insurance {2}. "
                        "Please create an Insurance Claim instead of direct invoice."
                    ).format(item.item_code, item_group, insurance_doc.name))

def handle_billable_service(doc, method):
    """Universal handler for billable healthcare services"""
    if not doc.patient:
        return

    # Get billable item based on document type
    billable_items = []
    
    if doc.doctype == "Lab Test":
        try:
            if not doc.template:
                frappe.throw(_("Lab Test Template is required for billing"))
                
            # First check if template exists
            if not frappe.db.exists("Lab Test Template", doc.template):
                frappe.throw(_("Lab Test Template {0} not found").format(doc.template))
                
            template = frappe.get_doc("Lab Test Template", doc.template)
            if template.is_billable:
                if not template.item:
                    frappe.throw(_("No billing item linked to Lab Test Template {0}").format(template.name))
                    
                # Verify item exists
                if not frappe.db.exists("Item", template.item):
                    frappe.throw(_("Billing Item {0} not found").format(template.item))
                    
                billable_items.append({
                    "item_code": template.item,
                    "item_name": template.lab_test_name,
                    "qty": 1,
                    "rate": template.lab_test_rate or 0,
                    "reference_dt": "Lab Test",
                    "reference_dn": doc.name
                })
                
            # Create stock entry for consumables if any
            create_lab_consumables_stock_entry(doc)
                
        except frappe.DoesNotExistError as e:
            frappe.throw(_("Error: {0}").format(str(e)))
        except Exception as e:
            frappe.log_error(f"Error processing Lab Test {doc.name}: {str(e)}")
            frappe.throw(_("Error processing Lab Test. Please check error logs."))
            
    elif doc.doctype == "Observation":
        try:
            if not doc.observation_template:
                frappe.throw(_("Observation Template is required for billing"))
                
            # First check if template exists
            if not frappe.db.exists("Observation Template", doc.observation_template):
                frappe.throw(_("Observation Template {0} not found").format(doc.observation_template))
                
            template = frappe.get_doc("Observation Template", doc.observation_template)
            if template.is_billable:
                if not template.item:
                    frappe.throw(_("No billing item linked to Observation Template {0}").format(template.name))
                    
                # Verify item exists
                if not frappe.db.exists("Item", template.item):
                    frappe.throw(_("Billing Item {0} not found").format(template.item))
                    
                billable_items.append({
                    "item_code": template.item,
                    "item_name": template.name,
                    "qty": 1,
                    "rate": template.rate or 0,
                    "reference_dt": "Observation",
                    "reference_dn": doc.name
                })
        except frappe.DoesNotExistError as e:
            frappe.throw(_("Error: {0}").format(str(e)))
        except Exception as e:
            frappe.log_error(f"Error processing Observation {doc.name}: {str(e)}")
            frappe.throw(_("Error processing Observation. Please check error logs."))
            
    elif doc.doctype == "Clinical Procedure":
        try:
            if not doc.procedure_template:
                frappe.throw(_("Clinical Procedure Template is required for billing"))
                
            # First check if template exists
            if not frappe.db.exists("Clinical Procedure Template", doc.procedure_template):
                frappe.throw(_("Clinical Procedure Template {0} not found").format(doc.procedure_template))
                
            template = frappe.get_doc("Clinical Procedure Template", doc.procedure_template)
            if template.is_billable:
                if not template.item:
                    frappe.throw(_("No billing item linked to Clinical Procedure Template {0}").format(template.name))
                    
                # Verify item exists
                if not frappe.db.exists("Item", template.item):
                    frappe.throw(_("Billing Item {0} not found").format(template.item))
                    
                billable_items.append({
                    "item_code": template.item,
                    "item_name": template.name,
                    "qty": 1,
                    "rate": template.rate or 0,
                    "reference_dt": "Clinical Procedure",
                    "reference_dn": doc.name
                })
        except frappe.DoesNotExistError as e:
            frappe.throw(_("Error: {0}").format(str(e)))
        except Exception as e:
            frappe.log_error(f"Error processing Clinical Procedure {doc.name}: {str(e)}")
            frappe.throw(_("Error processing Clinical Procedure. Please check error logs."))
            
    elif doc.doctype == "Therapy Session":
        therapy_type = frappe.get_doc("Therapy Type", doc.therapy_type)
        if therapy_type.is_billable:
            billable_items.append({
                "item_code": therapy_type.item,
                "item_name": therapy_type.therapy_type,
                "qty": 1,
                "rate": therapy_type.rate,
                "reference_dt": "Therapy Session",
                "reference_dn": doc.name
            })
            
    elif doc.doctype == "Patient Appointment":
        if doc.billing_item:
            rate = frappe.db.get_value("Item", doc.billing_item, "standard_rate") or 0
            billable_items.append({
                "item_code": doc.billing_item,
                "item_name": frappe.db.get_value("Item", doc.billing_item, "item_name"),
                "qty": 1,
                "rate": rate,
                "reference_dt": "Patient Appointment",
                "reference_dn": doc.name
            })
            
    elif doc.doctype == "Patient Encounter":
        if doc.billing_item:
            rate = frappe.db.get_value("Item", doc.billing_item, "standard_rate") or 0
            billable_items.append({
                "item_code": doc.billing_item,
                "item_name": frappe.db.get_value("Item", doc.billing_item, "item_name"),
                "qty": 1,
                "rate": rate,
                "reference_dt": "Patient Encounter",
                "reference_dn": doc.name
            })
            
    elif doc.doctype == "Vital Signs":
        if doc.billing_item:
            rate = frappe.db.get_value("Item", doc.billing_item, "standard_rate") or 0
            billable_items.append({
                "item_code": doc.billing_item,
                "item_name": frappe.db.get_value("Item", doc.billing_item, "item_name"),
                "qty": 1,
                "rate": rate,
                "reference_dt": "Vital Signs",
                "reference_dn": doc.name
            })

    if not billable_items:  # If no billable items found, return early
        return

    # Get the appropriate date field based on doctype
    service_date = None
    if hasattr(doc, 'posting_date'):
        service_date = doc.posting_date
    elif hasattr(doc, 'date'):
        service_date = doc.date
    elif hasattr(doc, 'encounter_date'):
        service_date = doc.encounter_date
    else:
        service_date = getdate()  # Default to today if no date field found

    # Check for active insurance coverage
    active_insurance = frappe.get_all(
        "Insurance Coverage",
        filters={
            "patient": doc.patient,
            "status": "Active",
            "docstatus": 1,
            "coverage_start_date": ["<=", service_date],
            "coverage_end_date": [">=", service_date]
        },
        fields=["name"],
        limit=1
    )

    if active_insurance:
        insurance_doc = frappe.get_doc("Insurance Coverage", active_insurance[0].name)
        
        # Separate items into insured and non-insured
        insured_items = []
        non_insured_items = []
        
        for item in billable_items:
            item_group = frappe.db.get_value("Item", item["item_code"], "item_group")
            is_covered = False
            
            # Check if item group is covered by insurance
            for covered_item in insurance_doc.covered_items:
                if covered_item.item_group == item_group:
                    is_covered = True
                    break
            
            if is_covered:
                insured_items.append(item)
            else:
                non_insured_items.append(item)

        # For non-insured items, create invoice
        if non_insured_items:
            create_sales_invoice(doc, non_insured_items, service_date)

        # Handle insured items
        if insured_items:
            create_insurance_claim(doc, insurance_doc, insured_items, service_date)

    else:
        # No active insurance - create direct invoice for all items
        create_sales_invoice(doc, billable_items, service_date)

def create_sales_invoice(doc, items, posting_date):
    """Create sales invoice for non-insured items"""
    customer = frappe.db.get_value("Patient", doc.patient, "customer")
    if not customer:
        frappe.throw(_("No customer linked to patient {0}").format(doc.patient))

    invoice = frappe.new_doc("Sales Invoice")
    invoice.patient = doc.patient
    invoice.customer = customer
    invoice.company = doc.company
    invoice.posting_date = posting_date
    invoice.due_date = posting_date

    for item in items:
        invoice.append("items", {
            "item_code": item["item_code"],
            "item_name": item["item_name"],
            "qty": item["qty"],
            "rate": item["rate"],
            "reference_dt": item["reference_dt"],
            "reference_dn": item["reference_dn"]
        })

    invoice.set_missing_values()
    invoice.set_taxes()
    invoice.insert()
    invoice.submit()
    
    # Link the invoice to the service document if custom field exists
    if hasattr(doc, 'custom_sales_invoice'):
        frappe.db.set_value(doc.doctype, doc.name, "custom_sales_invoice", invoice.name)
    
    frappe.msgprint(_("Created sales invoice {0} for billable items").format(invoice.name))

def create_insurance_claim(doc, insurance_doc, items, service_date):
    """Create or update insurance claim for insured items"""
    # Check for existing open claim for the day
    existing_claim = frappe.get_all(
        "Insurance Claim",
        filters={
            "insurance_coverage": insurance_doc.name,
            "patient": doc.patient,
            "claim_date": service_date,
            "docstatus": 0  # Draft status
        },
        limit=1
    )

    if existing_claim:
        claim = frappe.get_doc("Insurance Claim", existing_claim[0].name)
    else:
        claim = frappe.new_doc("Insurance Claim")
        claim.insurance_coverage = insurance_doc.name
        claim.patient = doc.patient
        claim.claim_date = service_date
        claim.company = doc.company

    # Add items to claim
    for item in items:
        claim.append("items", {
            "item_code": item["item_code"],
            "item_name": item["item_name"],
            "amount": item["qty"] * item["rate"],
            "reference_dt": item["reference_dt"],
            "reference_dn": item["reference_dn"]
        })

    if not existing_claim:
        claim.insert()
    else:
        claim.save()

    frappe.msgprint(_("Added covered items to insurance claim {0}").format(claim.name))

def create_lab_consumables_stock_entry(doc):
    """Create stock entry for lab test consumables"""
    if not hasattr(doc, 'custom_consumables') or not doc.custom_consumables:
        return
        
    # Check if any consumables have warehouse specified
    has_consumables_with_warehouse = False
    for item in doc.custom_consumables:
        if item.warehouse:
            has_consumables_with_warehouse = True
            break
            
    if not has_consumables_with_warehouse:
        return
        
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = "Material Issue"
    stock_entry.company = doc.company
    stock_entry.posting_date = frappe.utils.today()
    stock_entry.purpose = "Material Issue"
    stock_entry.reference_doctype = doc.doctype
    stock_entry.reference_docname = doc.name
    
    for item in doc.custom_consumables:
        if not item.warehouse:
            continue
            
        stock_entry.append("items", {
            "item_code": item.item,
            "qty": item.qty,
            "uom": item.uom,
            "s_warehouse": item.warehouse,
            "allow_zero_valuation_rate": 1
        })
    
    if stock_entry.items:
        stock_entry.insert()
        stock_entry.submit()
        frappe.msgprint(_("Stock Entry {0} created for consumables").format(
            frappe.bold(stock_entry.name)
        )) 