import frappe
from frappe.model.document import Document
from frappe.utils import flt

class InsuranceDeductibleUpdate(Document):
    def validate(self):
        self.validate_coverage()
        self.validate_amount()
        
    def validate_coverage(self):
        """Validate insurance coverage"""
        coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
        
        if coverage.status != "Active":
            frappe.throw(f"Insurance coverage {self.insurance_coverage} is {coverage.status}")
            
        # Validate claim belongs to this coverage
        if self.insurance_claim:
            claim = frappe.get_doc("Insurance Claim", self.insurance_claim)
            if claim.insurance_coverage != self.insurance_coverage:
                frappe.throw("Insurance claim does not belong to this coverage")
                
    def validate_amount(self):
        """Validate deductible amount"""
        coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
        
        if self.deductible_amount > 0:  # Deduction
            if flt(self.deductible_amount) > flt(coverage.deductible_remaining):
                frappe.throw(
                    f"Deductible amount {self.deductible_amount} cannot be greater than "
                    f"remaining deductible {coverage.deductible_remaining}"
                )
        elif self.deductible_amount < 0:  # Reversal
            if abs(flt(self.deductible_amount)) > flt(coverage.patient_deductible - coverage.deductible_remaining):
                frappe.throw(
                    f"Reversal amount {abs(self.deductible_amount)} cannot be greater than "
                    f"applied deductible {coverage.patient_deductible - coverage.deductible_remaining}"
                )
                
    def on_submit(self):
        """Update insurance coverage deductible"""
        coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
        coverage.deductible_remaining = flt(coverage.deductible_remaining) - flt(self.deductible_amount)
        coverage.save() 