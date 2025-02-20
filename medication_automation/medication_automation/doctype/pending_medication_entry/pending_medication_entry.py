import frappe
from frappe.model.document import Document

class PendingMedicationEntry(Document):
    def validate(self):
        self.validate_medication_entry()
        self.validate_status()
        
    def validate_medication_entry(self):
        """Validate medication entry exists and is not cancelled"""
        if not frappe.db.exists("Inpatient Medication Entry", self.medication_entry):
            frappe.throw(f"Medication Entry {self.medication_entry} does not exist")
            
        status = frappe.db.get_value("Inpatient Medication Entry", 
                                   self.medication_entry, 
                                   "docstatus")
        if status == 2:  # Cancelled
            frappe.throw(f"Medication Entry {self.medication_entry} is cancelled")
            
    def validate_status(self):
        """Validate status and reason"""
        if self.status == "Missed" and not self.reason:
            frappe.throw("Reason is required when marking medication as missed")
            
        if self.status != "Missed" and self.reason:
            self.reason = None  # Clear reason if status is not missed
            
    def on_update(self):
        """Update medication entry status"""
        if self.status == "Completed":
            # Mark the medication entry as completed
            medication_entry = frappe.get_doc("Inpatient Medication Entry", self.medication_entry)
            medication_entry.status = "Completed"
            medication_entry.save() 