import frappe
from frappe.model.document import Document

class InpatientMedicationConsumables(Document):
    def validate(self):
        self.calculate_amount()
    
    def calculate_amount(self):
        if self.billable and self.qty and self.rate:
            self.amount = self.qty * self.rate
        else:
            self.amount = 0 