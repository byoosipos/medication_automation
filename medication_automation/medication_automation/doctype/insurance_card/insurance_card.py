import frappe
from frappe.model.document import Document
from frappe.utils import getdate, flt

class InsuranceCard(Document):
    def validate(self):
        self.validate_dates()
        self.validate_coverage()
        
    def validate_dates(self):
        """Validate card validity dates"""
        if getdate(self.valid_from) > getdate(self.valid_till):
            frappe.throw("Valid Till date cannot be before Valid From date")
            
        # Set status based on dates
        today = getdate()
        if today < getdate(self.valid_from):
            self.status = "Pending"
        elif today > getdate(self.valid_till):
            self.status = "Expired"
            
    def validate_coverage(self):
        """Validate coverage details"""
        if self.coverage_type == "Co-Pay":
            if not self.copay_percent:
                frappe.throw("Co-pay Percentage is required for Co-Pay coverage type")
                
            if flt(self.copay_percent) <= 0:
                frappe.throw("Co-pay Percentage must be greater than zero")
                
            if flt(self.copay_percent) >= 100:
                frappe.throw("Co-pay Percentage must be less than 100%")
                
        # Validate deductible
        if self.deductible and flt(self.deductible) <= 0:
            frappe.throw("Deductible Amount must be greater than zero")
            
    def on_submit(self):
        """Check for overlapping active cards"""
        existing_cards = frappe.get_all(
            "Insurance Card",
            filters={
                "patient": self.patient,
                "insurance_company": self.insurance_company,
                "status": "Active",
                "docstatus": 1,
                "name": ["!=", self.name]
            }
        )
        
        if existing_cards:
            frappe.throw(
                f"Patient {self.patient} already has an active insurance card "
                f"with {self.insurance_company}"
            ) 