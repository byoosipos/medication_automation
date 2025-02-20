import frappe
from frappe.model.document import Document

class NursingShiftAssignment(Document):
    def validate(self):
        self.validate_user()
        self.validate_role()
        
    def validate_user(self):
        """Validate user exists and has nursing role"""
        if not frappe.db.exists("User", self.user):
            frappe.throw(f"User {self.user} does not exist")
            
        # Check if user has nursing role
        roles = frappe.get_roles(self.user)
        if "Nursing User" not in roles:
            frappe.throw(f"User {self.user} must have Nursing User role")
            
    def validate_role(self):
        """Validate role exists"""
        if not frappe.db.exists("Role", self.role):
            frappe.throw(f"Role {self.role} does not exist") 