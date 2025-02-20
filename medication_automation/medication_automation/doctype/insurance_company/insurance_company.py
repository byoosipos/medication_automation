import frappe
from frappe.model.document import Document
from frappe.contacts.address_and_contact import load_address_and_contact

class InsuranceCompany(Document):
    def onload(self):
        """Load address and contact info"""
        load_address_and_contact(self)
        
    def validate(self):
        self.validate_customer()
        self.validate_approval_settings()
        
    def validate_customer(self):
        """Validate customer exists and is a company"""
        if not frappe.db.exists("Customer", self.customer):
            frappe.throw(f"Customer {self.customer} does not exist")
            
        # Check if customer is already linked to another insurance company
        existing = frappe.db.exists("Insurance Company", {
            "customer": self.customer,
            "name": ["!=", self.name]
        })
        if existing:
            frappe.throw(f"Customer {self.customer} is already linked to Insurance Company {existing}")
            
        # Ensure customer is a company
        customer_type = frappe.db.get_value("Customer", self.customer, "customer_type")
        if customer_type != "Company":
            frappe.throw(f"Customer {self.customer} must be of type 'Company'")
            
    def validate_approval_settings(self):
        """Validate approval settings"""
        if self.requires_preapproval:
            if not self.auto_approval_limit:
                frappe.throw("Auto Approval Limit is required when Pre-approval is enabled")
                
            if not self.default_approval_validity_days:
                self.default_approval_validity_days = 30
                
            if self.default_approval_validity_days <= 0:
                frappe.throw("Approval Validity Days must be greater than zero")
                
        else:
            # Clear approval settings if pre-approval is disabled
            self.auto_approval_limit = 0
            self.default_approval_status = "Pending"
            
    def on_update(self):
        """Update linked records"""
        self.update_customer_details()
        
    def update_customer_details(self):
        """Update customer details from insurance company"""
        customer = frappe.get_doc("Customer", self.customer)
        
        # Update customer details
        if customer.customer_name != self.company_name:
            customer.customer_name = self.company_name
            
        if customer.tax_id != self.tax_id:
            customer.tax_id = self.tax_id
            
        if self.email and customer.email_id != self.email:
            customer.email_id = self.email
            
        if self.phone and customer.mobile_no != self.phone:
            customer.mobile_no = self.phone
            
        customer.save()
        
    def on_trash(self):
        """Prevent deletion if there are linked records"""
        # Check for insurance coverage
        coverage = frappe.db.exists("Insurance Coverage", {
            "insurance_company": self.name,
            "docstatus": ["!=", 2]  # Not cancelled
        })
        if coverage:
            frappe.throw("Cannot delete Insurance Company with active coverage records")
            
        # Check for insurance claims
        claims = frappe.db.exists("Insurance Claim", {
            "insurance_company": self.name,
            "docstatus": ["!=", 2]  # Not cancelled
        })
        if claims:
            frappe.throw("Cannot delete Insurance Company with existing claims") 