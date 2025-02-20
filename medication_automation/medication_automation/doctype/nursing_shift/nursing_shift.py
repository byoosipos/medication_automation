import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, add_to_date, getdate
from hrms.hr.doctype.shift_assignment.shift_assignment import get_shift_assignments

class NursingShift(Document):
    def validate(self):
        self.validate_shift_schedule()
        self.validate_nurses()
        self.validate_service_unit()
        self.update_patient_list()
        
    def validate_shift_schedule(self):
        """Validate shift schedule and fetch related details"""
        if not self.shift_schedule:
            frappe.throw("Shift Schedule is required")
            
        schedule = frappe.get_doc("Shift Schedule", self.shift_schedule)
        
        # Set shift type and times from schedule
        if schedule.shift_type:
            self.shift_type = schedule.shift_type
            shift_type = frappe.get_doc("Shift Type", schedule.shift_type)
            self.start_time = shift_type.start_time
            self.end_time = shift_type.end_time
        
        # Auto-populate nurses from shift schedule
        self.populate_nurses_from_schedule()
        
    def populate_nurses_from_schedule(self):
        """Auto-populate nurses from shift schedule assignments"""
        if not self.shift_schedule or not self.shift_date:
            return
            
        # Get all employees assigned to this shift type for the date
        assignments = frappe.get_all(
            "Shift Assignment",
            filters={
                "shift_type": self.shift_type,
                "start_date": ["<=", self.shift_date],
                "end_date": [">=", self.shift_date],
                "docstatus": 1,
                "status": "Active"
            },
            fields=["name", "employee"]
        )
        
        if not assignments:
            return
            
        # Clear existing nurses if any
        self.nurses = []
        
        # Add each assigned employee to nurses
        for assignment in assignments:
            employee = frappe.db.get_value("Employee", 
                assignment.employee, 
                ["name", "user_id", "company"], 
                as_dict=1
            )
            
            # Set company from first nurse's company if not set
            if not self.company and employee and employee.company:
                self.company = employee.company
                
            self.append("nurses", {
                "shift_assignment": assignment.name,
                "employee": assignment.employee,
                "shift_start": self.start_time,
                "shift_end": self.end_time,
                "shift_date": self.shift_date
            })
                
    def validate_nurses(self):
        """Ensure at least one nurse is assigned"""
        if not self.nurses:
            frappe.throw("At least one nurse must be assigned to the shift")
            
        for nurse in self.nurses:
            if not nurse.shift_assignment:
                frappe.throw("Shift Assignment is required for all nurses")
                
    def validate_service_unit(self):
        """Check if service unit is valid"""
        if not frappe.db.exists("Healthcare Service Unit", self.service_unit):
            frappe.throw(f"Service Unit {self.service_unit} does not exist")
            
    def update_patient_list(self):
        """Update list of patients for the shift"""
        if not self.shift_date:
            return
            
        # If we already have patients, don't overwrite their status
        existing_patients = {
            p.patient: {
                "condition": p.condition,
                "medication_status": p.medication_status,
                "special_instructions": p.special_instructions
            } for p in self.patients
        }
            
        # Get all patients registered today
        patients = frappe.get_all(
            "Patient",
            filters={
                "creation": ["like", f"{self.shift_date}%"],
                "status": "Active"
            },
            fields=["name as patient", "patient_name"],
            distinct=True
        )
        
        # Also get patients with encounters for the day
        patients_with_encounters = frappe.get_all(
            "Patient Encounter",
            filters={
                "encounter_date": self.shift_date,
                "docstatus": 1,
                "company": self.company
            },
            fields=["patient", "patient_name"],
            distinct=True
        )
        
        # Merge both lists (avoiding duplicates)
        patient_map = {p.patient: p for p in patients}
        for p in patients_with_encounters:
            if p.patient not in patient_map:
                patient_map[p.patient] = p
                
        # Clear existing patients if this is a new shift
        if not self.is_new:
            self.patients = []
        
        # Add all patients
        for patient in patient_map.values():
            existing = existing_patients.get(patient.patient, {})
            self.append("patients", {
                "patient": patient.patient,
                "patient_name": patient.patient_name,
                "condition": existing.get("condition", "Stable"),
                "medication_status": existing.get("medication_status", "Not Started"),
                "special_instructions": existing.get("special_instructions", "")
            })
                
    def before_insert(self):
        """Check for overlapping shifts"""
        if self.shift_type == "Night":
            next_day = add_to_date(self.shift_date, days=1)
            existing_shift = frappe.db.exists("Nursing Shift", {
                "service_unit": self.service_unit,
                "shift_date": ["in", [self.shift_date, next_day]],
                "shift_type": self.shift_type,
                "docstatus": ["!=", 2]
            })
        else:
            existing_shift = frappe.db.exists("Nursing Shift", {
                "service_unit": self.service_unit,
                "shift_date": self.shift_date,
                "shift_type": self.shift_type,
                "docstatus": ["!=", 2]
            })
        
        if existing_shift:
            frappe.throw(f"A {self.shift_type} shift already exists for {self.service_unit} on {self.shift_date}")
            
    def on_submit(self):
        """Start the shift"""
        pass
            
    def on_update_after_submit(self):
        """Handle shift status changes"""
        if self.status == "Closed":
            self.create_handover_document()
            
    def create_handover_document(self):
        """Create handover document for next shift"""
        next_shift_type = "Night" if self.shift_type == "Day" else "Day"
        next_shift_date = add_to_date(self.shift_date, days=1) if self.shift_type == "Night" else self.shift_date
            
        handover = frappe.get_doc({
            "doctype": "Nursing Handover",
            "from_shift": self.name,
            "shift_type": next_shift_type,
            "shift_date": next_shift_date,
            "service_unit": self.service_unit,
            "handover_notes": self.handover_notes
        })
        
        # Copy patients - only those not completed
        for patient in self.patients:
            if patient.medication_status != "Completed":
                handover.append("patients", {
                    "patient": patient.patient,
                    "patient_name": patient.patient_name,
                    "patient_type": patient.patient_type,
                    "bed": patient.bed,
                    "condition": patient.condition,
                    "medication_status": "Not Started",  # Reset status for new shift
                    "special_instructions": patient.special_instructions
                })
            
        handover.insert() 