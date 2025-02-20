import frappe
from frappe.model.document import Document

class InsuranceCoverageItem(Document):
    def validate(self):
        self.validate_percentage()
        self.validate_max_amount()
        
    def validate_percentage(self):
        """Validate coverage percentage"""
        if self.coverage_percentage <= 0:
            frappe.throw("Coverage percentage must be greater than zero")
            
        if self.coverage_percentage > 100:
            frappe.throw("Coverage percentage cannot exceed 100%")
            
    def validate_max_amount(self):
        """Validate maximum amount if specified"""
        if self.max_amount and self.max_amount <= 0:
            frappe.throw("Maximum amount must be greater than zero") 