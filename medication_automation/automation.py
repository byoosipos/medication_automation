import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, get_datetime, get_time, getdate, add_days
from healthcare.healthcare.doctype.prescription_duration.prescription_duration import PrescriptionDuration
import json

def get_frequency_times(frequency, start_time):
    """
    Calculate administration times based on frequency pattern
    Example: 1-1-1 means 3 doses spread across the day starting from start_time
    Returns list of tuples with (time, dosage)
    """
    if not frequency:
        return [("09:00:00", 1)]
        
    base_time = get_time(start_time) if start_time else get_time('09:00:00')
    times_and_doses = []
    
    # Parse frequency like 1-1-2-1 or 1-0-1
    doses = [int(d) for d in str(frequency).split('-') if d.isdigit()]
    if not doses:
        return [(base_time.strftime('%H:%M:%S'), 1)]
    
    # Calculate interval based on number of doses
    total_slots = len(doses)  # Use total slots instead of non-zero doses
    if total_slots <= 1:
        return [(base_time.strftime('%H:%M:%S'), doses[0])]
    
    # Calculate time intervals based on start time
    hours_interval = 24 // total_slots  # e.g., for 1-1-1 this will be 8 hours
    current_time = get_datetime(f"2000-01-01 {base_time}")
    
    # Create entries for each dose
    for i, dose in enumerate(doses):
        if dose > 0:  # Only create entries for non-zero doses
            adjusted_time = add_to_date(current_time, hours=(i * hours_interval))
            times_and_doses.append((adjusted_time.time().strftime('%H:%M:%S'), dose))
    
    return sorted(times_and_doses, key=lambda x: x[0])  # Sort by time

def get_or_create_prescription_dosage(dosage_pattern):
    """
    Get existing Prescription Dosage pattern.
    No new patterns will be created - only use existing ones.
    """
    if not dosage_pattern:
        return "Once Daily"  # Default dosage
        
    # Only use existing patterns
    if frappe.db.exists("Prescription Dosage", dosage_pattern):
        return dosage_pattern
    else:
        frappe.msgprint(f"Dosage pattern {dosage_pattern} not found, using Once Daily")
        return "Once Daily"  # Fallback to default if pattern doesn't exist

def get_duration_details(period):
    """
    Get duration details from standard Prescription Duration records
    Returns tuple of (number, unit, total_hours)
    Example: '8 Hour' -> (8, 'Hour', 8)
            '3 Day' -> (3, 'Day', 72)
    """
    if not period:
        return (0, None, 0)
        
    try:
        duration = frappe.get_doc("Prescription Duration", period)
        if not duration:
            return (0, None, 0)
            
        # Get the number and period type
        number = duration.number
        period_type = duration.period  # 'Hour', 'Day', 'Week', or 'Month'
        
        # Calculate total hours based on period type
        total_hours = duration.get_hours()
            
        return (number, period_type, total_hours)
    except Exception as e:
        frappe.log_error(f"Error getting duration for {period}: {str(e)}")
        return (0, None, 0)

def calculate_doses_for_duration(dosage_pattern, period, start_datetime):
    """
    Calculate doses based on pattern and duration type
    Handles different period types (Hour, Day, Week, Month) and patterns
    """
    number, period_type, total_hours = get_duration_details(period)
    if not total_hours or not period_type:
        return []
        
    doses = get_doses_from_pattern(dosage_pattern)
    if not doses:
        return []
    
    # Remove zero doses from pattern but keep original spacing
    non_zero_indices = [i for i, dose in enumerate(doses) if dose > 0]
    if not non_zero_indices:
        return []
    
    doses_per_day = len(doses)  # Keep original spacing
    hours_between_doses = 24 // doses_per_day if doses_per_day > 0 else 24
    
    result_doses = []
    
    if period_type == 'Hour':
        # For hourly durations, only include doses that would occur within the period
        current_hour = 0
        while current_hour < total_hours:
            dose_index = (current_hour // hours_between_doses) % doses_per_day
            if doses[dose_index] > 0:  # Only add non-zero doses
                dose_time = add_to_date(start_datetime, hours=current_hour)
                if (dose_time - start_datetime).total_seconds() / 3600 <= total_hours:
                    result_doses.append({
                        'datetime': dose_time,
                        'units': doses[dose_index]
                    })
            current_hour += hours_between_doses
    else:
        # For Day, Week, Month - calculate full days of doses
        total_days = total_hours // 24
        for day in range(total_days):
            for dose_index, dose in enumerate(doses):
                if dose > 0:  # Only add non-zero doses
                    hours_from_start = (day * 24) + (dose_index * hours_between_doses)
                    dose_time = add_to_date(start_datetime, hours=hours_from_start)
                    result_doses.append({
                        'datetime': dose_time,
                        'units': dose
                    })
    
    return sorted(result_doses, key=lambda x: x['datetime'])

def get_prescription_dates(period, start_date=None):
    """
    Get list of dates for the prescription period starting from start_date
    Uses standard Prescription Duration records for accurate calculations
    """
    if not period or not start_date:
        return []
    
    days = get_duration_in_hours(period) // 24
    if not days:
        return []
        
    dates = []
    start = getdate(start_date)
    for i in range(int(days)):
        dates.append(add_days(start, i))
    return dates

def get_doses_from_pattern(dosage_pattern):
    """
    Parse dosage pattern like 1-0-0 or 2-2-2 and return list of doses
    Returns list of integers representing units per dose
    """
    if not dosage_pattern:
        return [1]
    return [int(d) for d in str(dosage_pattern).split('-') if d.isdigit()]

@frappe.whitelist()
def create_inpatient_medication_order(encounter, start_date=None, start_time=None, drug_schedules=None):
    """
    Create Inpatient Medication Order with proper handling of individual drug schedules
    start_date and start_time are defaults/fallbacks if individual drug schedule is not specified
    """
    encounter_doc = frappe.get_doc("Patient Encounter", encounter)
    
    if not encounter_doc.drug_prescription:
        frappe.throw(_("No drugs prescribed in this encounter"))
    
    # Create Inpatient Medication Order
    medication_order = frappe.new_doc("Inpatient Medication Order")
    medication_order.patient = encounter_doc.patient
    medication_order.patient_encounter = encounter_doc.name
    medication_order.company = encounter_doc.company
    
    # Default start date is used only for the document, not for individual drugs
    medication_order.start_date = start_date or encounter_doc.encounter_date
    
    # Convert drug_schedules from string to dict if needed
    if isinstance(drug_schedules, str):
        import json
        drug_schedules = json.loads(drug_schedules)
    
    # Create a map of drug_code to schedule for easy lookup
    schedule_map = {}
    if drug_schedules:
        schedule_map = {schedule['drug_code']: schedule for schedule in drug_schedules}
    
    latest_end_date = None
    for drug in encounter_doc.drug_prescription:
        # Get the specific schedule for this drug
        drug_schedule = schedule_map.get(drug.drug_code, {})
        
        # Priority for start date and time:
        # 1. Individual drug schedule from the dialog
        # 2. Default values from the dialog
        # 3. Encounter date and default time "09:00:00"
        drug_start_date = (
            drug_schedule.get('start_date') or  # Individual drug start date
            start_date or                       # Default start date
            encounter_doc.encounter_date        # Fallback to encounter date
        )
        
        drug_start_time = (
            drug_schedule.get('start_time') or  # Individual drug start time
            start_time or                       # Default start time
            "09:00:00"                         # Fallback time
        )
        
        if drug.dosage:
            try:
                start_datetime = get_datetime(f"{drug_start_date} {drug_start_time}")
                
                # Calculate doses based on period type and duration
                doses = calculate_doses_for_duration(
                    drug.dosage,
                    drug.period,
                    start_datetime
                )
                
                # Create medication orders for each dose
                for dose in doses:
                    medication_order.append("medication_orders", {
                        "drug": drug.drug_code,
                        "drug_name": drug.drug_name,
                        "dosage": dose['units'],
                        "period": drug.period,
                        "dosage_form": drug.dosage_form,
                        "date": dose['datetime'].date(),
                        "time": dose['datetime'].strftime("%H:%M:%S"),
                        "comment": drug.comment
                    })
                
                if doses:
                    end_date = doses[-1]['datetime'].date()
                    if not latest_end_date or end_date > latest_end_date:
                        latest_end_date = end_date
                        
            except Exception as e:
                frappe.log_error(
                    f"Error creating medication order for {drug.drug_code} "
                    f"(start: {drug_start_date} {drug_start_time}): {str(e)}"
                )
                continue
    
    # Set the final end date to the latest one
    if latest_end_date:
        medication_order.end_date = latest_end_date
    
    medication_order.insert()
    medication_order.submit()
    
    return medication_order.name

@frappe.whitelist()
def get_active_medications(encounter):
    """
    Get list of active medications for an encounter
    Returns medications that are:
    1. Not completed
    2. Scheduled for today or future dates
    3. From active medication orders
    """
    try:
        if not encounter:
            frappe.throw(_("Patient encounter is required"))

        # Get all medication orders for this encounter
        medication_orders = frappe.get_all(
            "Inpatient Medication Order",
            filters={
                "patient_encounter": encounter,
                "docstatus": 1,  # Submitted
                "custom_treatment_status": "Active"
            },
            fields=["name", "patient", "start_date", "end_date"]
        )
        
        if not medication_orders:
            frappe.msgprint(_("No active medication orders found for this encounter"))
            return []
        
        active_medications = []
        today = frappe.utils.today()
        
        for order in medication_orders:
            # Get medication entries that are not completed
            entries = frappe.get_all(
                "Inpatient Medication Order Entry",
                filters={
                    "parent": order.name,
                    "is_completed": 0,
                    "date": [">=", today]  # Only future/today medications
                },
                fields=[
                    "name", "drug", "drug_name", "dosage", "period", 
                    "date", "time", "dosage_form", "comment", "instructions"
                ]
            )
            
            # Add order details to each entry
            for entry in entries:
                entry.order_name = order.name
                entry.patient = order.patient
                entry.start_date = order.start_date
                entry.end_date = order.end_date
                
                # Format the schedule time for display
                entry.schedule_datetime = f"{entry.date} {entry.time}"
                
                # Add to active medications
                active_medications.append(entry)
        
        # Sort by date and time
        active_medications.sort(key=lambda x: (x.date, x.time))
        
        if not active_medications:
            frappe.msgprint(_("No active medications found that can be stopped"))
            
        return active_medications
        
    except Exception as e:
        frappe.log_error(
            f"Error fetching active medications for encounter {encounter}: {str(e)}",
            "Get Active Medications Error"
        )
        frappe.throw(_("Error fetching active medications. Please check error logs."))
        return []

@frappe.whitelist()
def stop_medication(encounter, reason, medication_entries=None):
    """
    Stop auto-creation of medication entries for specific medications in an encounter
    Updates Inpatient Medication Order Entry status
    Args:
        encounter: Patient Encounter ID
        reason: Reason for stopping medications
        medication_entries: List of Inpatient Medication Order Entry IDs to stop
    """
    try:
        if not encounter:
            frappe.throw(_("Patient encounter is required"))
            
        if not reason:
            frappe.throw(_("Please provide a reason for stopping medications"))
            
        if isinstance(medication_entries, str):
            try:
                medication_entries = json.loads(medication_entries)
            except Exception:
                frappe.throw(_("Invalid medication entries format"))
            
        if not medication_entries or not isinstance(medication_entries, list):
            frappe.throw(_("Please select medications to stop"))
            
        # Get all medication orders for this encounter
        medication_orders = frappe.get_all(
            "Inpatient Medication Order",
            filters={
                "patient_encounter": encounter,
                "docstatus": 1,  # Submitted
                "custom_treatment_status": "Active"
            }
        )
        
        if not medication_orders:
            frappe.throw(_("No active medication orders found for this encounter"))
            
        medications_stopped = False
        for order in medication_orders:
            order_doc = frappe.get_doc("Inpatient Medication Order", order.name)
            
            # Mark selected entries as completed
            entries_modified = False
            for entry in order_doc.medication_orders:
                if entry.name in medication_entries:
                    if not entry.is_completed:  # Only modify if not already completed
                        entry.is_completed = 1
                        entries_modified = True
                        medications_stopped = True
            
            if entries_modified:
                # Add comment about stopped medications
                stopped_meds = [
                    f"{entry.drug_name} ({entry.dosage} {entry.period or 'As Needed'})"
                    for entry in order_doc.medication_orders
                    if entry.name in medication_entries
                ]
                comment = f'Medications stopped: {", ".join(stopped_meds)}\nReason: {reason}'
                order_doc.add_comment('Comment', text=comment)
                
                # Check if all medications in this order are completed
                all_completed = all(entry.is_completed for entry in order_doc.medication_orders)
                if all_completed:
                    order_doc.custom_treatment_status = "Stopped"
                
                order_doc.save()
        
        if not medications_stopped:
            frappe.throw(_("No medications were stopped. They may have already been completed."))
            
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error stopping medications for encounter {encounter}: {str(e)}\n"
            f"Medication entries: {medication_entries}",
            "Medication Stop Error"
        )
        raise

def check_medication_status(encounter):
    """
    Check if medication auto-creation is active for an encounter
    Returns True if any order is active, False if all are stopped
    """
    try:
        # Check if there are any active medication orders
        active_orders = frappe.get_all(
            "Inpatient Medication Order",
            filters={
                "patient_encounter": encounter,
                "docstatus": 1,  # Submitted
                "custom_treatment_status": "Active"
            },
            limit=1
        )
        return bool(active_orders)
    except Exception:
        return False  # Default to inactive if can't check 

def get_patient_service_unit(inpatient_record):
    """
    Get the current service unit for an inpatient
    Returns the service unit from the latest Inpatient Occupancy
    """
    if not inpatient_record:
        frappe.logger().debug(f"No inpatient record provided to get_patient_service_unit")
        return None
        
    try:
        # Get latest occupancy
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
            frappe.logger().debug(f"No active occupancy found for inpatient record {inpatient_record}")
            return None
            
        frappe.logger().debug(f"Found service unit {occupancy[0].service_unit} for inpatient record {inpatient_record}")
        return occupancy[0].service_unit
        
    except Exception as e:
        frappe.logger().error(f"Error getting service unit for inpatient record {inpatient_record}: {str(e)}")
        return None 