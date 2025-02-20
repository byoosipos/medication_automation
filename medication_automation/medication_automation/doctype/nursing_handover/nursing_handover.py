import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

class NursingHandover(Document):
    def validate(self):
        self.validate_shift()
        self.validate_service_unit()
        if not self.handover_time:
            self.handover_time = now_datetime()
        
    def validate_shift(self):
        """Validate shift details"""
        if not self.from_shift:
            frappe.throw("Source shift is required")
            
        shift = frappe.get_doc("Nursing Shift", self.from_shift)
        
        if shift.service_unit != self.service_unit:
            frappe.throw("Service Unit must match the source shift")
            
        if shift.status != "Closed":
            frappe.throw("Can only create handover from closed shifts")
            
        # Set shift type and date from source shift
        self.from_shift_type = shift.shift_type
        self.from_date = shift.shift_date
        
        # Set next shift type
        self.to_shift_type = "Night" if shift.shift_type == "Day" else "Day"
        self.to_date = shift.shift_date
        
        # Copy completed medications from shift
        self.completed_medications = []
        for med in shift.completed_medications:
            self.append("completed_medications", {
                "patient": med.patient,
                "patient_name": med.patient_name,
                "medication": med.medication,
                "dosage": med.dosage,
                "time_given": med.time_given,
                "given_by": med.given_by
            })
            
    def validate_service_unit(self):
        """Check if service unit is valid"""
        if not frappe.db.exists("Healthcare Service Unit", self.service_unit):
            frappe.throw(f"Service Unit {self.service_unit} does not exist")
            
    def before_insert(self):
        """Set initial values"""
        if not self.handover_status:
            self.handover_status = "Pending"
            
    def on_submit(self):
        """Create new shift after handover is submitted"""
        try:
            shift = frappe.get_doc("Nursing Shift", self.from_shift)
            
            # Create new shift
            new_shift = frappe.get_doc({
                "doctype": "Nursing Shift",
                "shift_type": self.to_shift_type,
                "shift_date": self.to_date,
                "service_unit": self.service_unit,
                "company": shift.company,
                "status": "In Progress"
            })
            
            # Copy patients that need continued care
            for patient in self.patients:
                if patient.medication_status != "Completed":
                    new_shift.append("patients", {
                        "patient": patient.patient,
                        "patient_name": patient.patient_name,
                        "condition": patient.condition,
                        "medication_status": "Not Started",  # Reset for new shift
                        "special_instructions": patient.special_instructions
                    })
                
            new_shift.insert()
            frappe.msgprint(f"New {self.to_shift_type} shift created successfully")
        except Exception as e:
            frappe.throw(f"Error creating new shift: {e}") 