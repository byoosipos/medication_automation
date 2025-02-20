import frappe
from frappe.model.document import Document

class InsuranceClaimItem(Document):
    def validate(self):
        self.validate_amounts()
        self.validate_approval()
        
    def validate_amounts(self):
        """Validate amounts"""
        if self.amount <= 0:
            frappe.throw("Amount must be greater than zero")
            
        if self.coverage_percentage <= 0:
            frappe.throw("Coverage percentage must be greater than zero")
            
        if self.coverage_percentage > 100:
            frappe.throw("Coverage percentage cannot exceed 100%")
            
    def validate_approval(self):
        """Validate approval details"""
        if self.approval_required and not self.approval_status:
            self.approval_status = "Pending"
            
        if not self.approval_required:
            self.approval_status = None
            self.approval_validity = None
            self.approval_remarks = None 