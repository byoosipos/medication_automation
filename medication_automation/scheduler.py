import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, add_to_date, getdate
from datetime import datetime
from .automation import check_medication_status, get_patient_service_unit

def create_medication_entries(check_missed_entries=True):
    """
    Scheduler job to create medication entries
    Runs every minute to create entries for medications due at the exact time
    Args:
        check_missed_entries: If True, also check for missed entries from past 6 hours
    """
    current_datetime = now_datetime()
    next_minute = add_to_date(current_datetime, minutes=1)
    
    # If checking missed entries, look back up to 6 hours
    if check_missed_entries:
        start_time = add_to_date(current_datetime, hours=-6)
        frappe.logger().info(f"Checking missed medication entries from {start_time} to {current_datetime}")
    else:
        start_time = current_datetime
    
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
            
        # Get medication orders due in the time window
        due_medications = frappe.get_all(
            "Inpatient Medication Order Entry",
            filters=[
                ["parent", "=", order.name],
                ["date", "=", current_datetime.date()],
                ["time", ">=", start_time.time().strftime("%H:%M:%S")],
                ["time", "<", next_minute.time().strftime("%H:%M:%S")],
                ["is_completed", "=", 0]
            ],
            fields=["name", "drug", "drug_name", "dosage", "dosage_form", "date", "time"]
        )
        
        if due_medications:
            try:
                # Group medications by time to create separate entries
                medications_by_time = {}
                for med in due_medications:
                    # Handle both string and datetime time formats
                    if isinstance(med.time, str):
                        time_key = med.time
                    elif hasattr(med.time, 'strftime'):  # datetime or time object
                        time_key = med.time.strftime("%H:%M:%S")
                    else:  # timedelta object
                        total_seconds = int(med.time.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        time_key = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        
                    if time_key not in medications_by_time:
                        medications_by_time[time_key] = []
                    medications_by_time[time_key].append(med)
                
                # Create separate entries for each time
                for time_key, medications in medications_by_time.items():
                    # Check if an entry already exists for this time
                    existing_entry = frappe.get_all(
                        "Inpatient Medication Entry",
                        filters={
                            "patient": order.patient,
                            "posting_date": current_datetime.date(),
                            "custom_scheduled_time": time_key,
                            "docstatus": ["!=", 2]  # Not cancelled
                        },
                        fields=["name", "medication_orders"]
                    )
                    
                    if existing_entry:
                        # Check if all medications are already included
                        existing_doc = frappe.get_doc("Inpatient Medication Entry", existing_entry[0].name)
                        existing_meds = [m.against_imoe for m in existing_doc.medication_orders]
                        new_meds = [m for m in medications if m.name not in existing_meds]
                        
                        if not new_meds:
                            # All medications already included, skip
                            continue
                            
                        # Add only new medications to existing entry
                        for medication in new_meds:
                            existing_doc.append("medication_orders", {
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
                        existing_doc.save()
                        continue
                    
                    # Create new entry if none exists
                    entry = frappe.get_doc({
                        "doctype": "Inpatient Medication Entry",
                        "patient": order.patient,
                        "patient_encounter": order.patient_encounter,
                        "company": order_doc.company,
                        "posting_date": current_datetime.date(),
                        "service_unit": service_unit,
                        "medication_orders": [],
                        "custom_scheduled_time": time_key
                    })
                    
                    for medication in medications:
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
                    
                    frappe.logger().debug(f"Creating medication entry with service unit {service_unit} for patient {order.patient} scheduled at {time_key}")
                    entry.insert()
                
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
        # First handle current minute
        create_medication_entries(check_missed_entries=False)
        # Then check for missed entries from last hour
        create_medication_entries(check_missed_entries=True)
        frappe.logger().debug("Medication entries created successfully")
    except Exception as e:
        frappe.logger().error(f"Error in medication entry scheduler: {str(e)}")
        frappe.log_error(f"Error in medication entry scheduler: {str(e)}", "Medication Scheduler Error")

def create_daily_medication_stock_requisition():
    """
    Creates a draft Stock Entry (Material Transfer) at configured time daily for all medications 
    needed for inpatient medication orders scheduled for that day.
    """
    try:
        # Get Medication Automation Settings
        settings = frappe.get_single("Medication Automation Settings")
        
        # Check if we should run on weekends
        if not settings.enable_weekend_scheduling:
            if frappe.utils.get_datetime().weekday() in [5, 6]:  # Saturday = 5, Sunday = 6
                frappe.logger().info("Skipping weekend stock requisition as per settings")
                return
                
        # Check pharmacy warehouse
        if not settings.default_pharmacy_warehouse:
            frappe.log_error("Default Pharmacy Warehouse not set in Medication Automation Settings", 
                           "Stock Requisition Creation Error")
            return

        # Get all active inpatient medication orders
        orders = frappe.get_all(
            "Inpatient Medication Order",
            filters={
                "docstatus": 1,  # Submitted
                "custom_treatment_status": "Active"
            },
            fields=["name", "patient", "company"]
        )

        if not orders:
            return

        # Dictionary to store aggregated medication requirements
        medications_needed = {}
        current_date = frappe.utils.getdate()
        
        for order in orders:
            # Get medications scheduled for today
            medications = frappe.get_all(
                "Inpatient Medication Order Entry",
                filters=[
                    ["parent", "=", order.name],
                    ["date", "=", current_date],
                    ["is_completed", "=", 0]
                ],
                fields=["drug", "drug_name", "dosage", "dosage_form"]
            )

            # Get service unit warehouse
            inpatient_record = frappe.db.get_value("Patient", order.patient, "inpatient_record")
            if not inpatient_record:
                continue

            service_unit = frappe.db.get_value(
                "Inpatient Occupancy",
                {
                    "parent": inpatient_record,
                    "left": 0
                },
                "service_unit"
            )

            if not service_unit:
                continue

            to_warehouse = frappe.db.get_value(
                "Healthcare Service Unit",
                service_unit,
                "warehouse"
            )

            if not to_warehouse:
                frappe.log_error(
                    f"No warehouse linked to service unit {service_unit}",
                    "Stock Requisition Creation Error"
                )
                continue

            # Aggregate medications
            for med in medications:
                key = (med.drug, to_warehouse)
                if key not in medications_needed:
                    medications_needed[key] = {
                        "drug_name": med.drug_name,
                        "total_qty": 0,
                        "dosage_form": med.dosage_form
                    }
                medications_needed[key]["total_qty"] += med.dosage

        if not medications_needed:
            return

        # Create Stock Entry
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = "Material Transfer"
        stock_entry.stock_entry_type = "Material Transfer"
        stock_entry.from_warehouse = settings.default_pharmacy_warehouse
        stock_entry.company = orders[0].company
        stock_entry.custom_is_medication_requisition = 1
        stock_entry.posting_date = current_date
        
        # Add pharmacy user if configured
        if settings.default_pharmacy_user:
            stock_entry.owner = settings.default_pharmacy_user

        # Add items to stock entry
        for (drug_code, to_warehouse), details in medications_needed.items():
            # Get item details
            uom = frappe.db.get_value("Item", drug_code, "stock_uom")
            
            # Check low stock threshold
            if settings.notify_low_stock:
                current_stock = get_stock_balance(drug_code, settings.default_pharmacy_warehouse)
                if current_stock <= settings.low_stock_threshold:
                    notify_low_stock(drug_code, current_stock, settings)
            
            stock_entry.append("items", {
                "item_code": drug_code,
                "item_name": details["drug_name"],
                "qty": details["total_qty"],
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1.0,
                "from_warehouse": settings.default_pharmacy_warehouse,
                "to_warehouse": to_warehouse,
                "custom_dosage_form": details["dosage_form"]
            })

        stock_entry.save()
        
        # Auto submit if configured
        if settings.auto_close_stock_entry:
            stock_entry.submit()
            
        # Create nursing task if configured
        if settings.auto_create_nursing_task:
            create_pharmacy_verification_task(stock_entry.name, settings)
            
        frappe.db.commit()
        
        # Send email notification if enabled
        if settings.enable_email_notifications and settings.notification_email_list:
            notify_stock_requisition_created(stock_entry.name, settings)
        
        frappe.logger().info(f"Created daily medication stock requisition: {stock_entry.name}")

    except Exception as e:
        frappe.log_error(
            f"Error creating daily medication stock requisition: {str(e)}",
            "Stock Requisition Creation Error"
        )

def get_stock_balance(item_code, warehouse):
    """Get current stock balance for an item in a warehouse"""
    return frappe.db.get_value("Bin", 
        {"item_code": item_code, "warehouse": warehouse},
        "actual_qty") or 0

def notify_low_stock(item_code, current_stock, settings):
    """Send low stock notification"""
    if settings.enable_email_notifications and settings.notification_email_list:
        subject = f"Low Stock Alert: {item_code}"
        message = f"Current stock level for {item_code} is {current_stock}, which is below the threshold of {settings.low_stock_threshold}"
        
        frappe.sendmail(
            recipients=settings.notification_email_list.split(','),
            subject=subject,
            message=message
        )
    
    frappe.msgprint(
        f"Low stock alert for {item_code}: Current stock {current_stock}",
        alert=True
    )

def notify_stock_requisition_created(stock_entry_name, settings):
    """Send email notification for created stock requisition"""
    subject = f"Medication Stock Requisition Created: {stock_entry_name}"
    message = f"A new medication stock requisition {stock_entry_name} has been created and requires review."
    
    frappe.sendmail(
        recipients=settings.notification_email_list.split(','),
        subject=subject,
        message=message
    )

def create_pharmacy_verification_task(stock_entry_name, settings):
    """Create a nursing task for pharmacy verification"""
    if not settings.nursing_task_role:
        return
        
    frappe.get_doc({
        "doctype": "Nursing Task",
        "description": f"Verify medication stock requisition: {stock_entry_name}",
        "task_type": "Pharmacy Verification",
        "status": "Open",
        "reference_doctype": "Stock Entry",
        "reference_name": stock_entry_name,
        "role": settings.nursing_task_role
    }).insert()

        