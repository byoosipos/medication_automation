import frappe
from frappe.model.document import Document

class MedicationAutomationSettings(Document):
    def validate(self):
        self.validate_email_list()
        self.validate_stock_requisition_time()
        
    def validate_email_list(self):
        """Validate email list format"""
        if self.enable_email_notifications and self.notification_email_list:
            emails = [email.strip() for email in self.notification_email_list.split(',')]
            for email in emails:
                if not frappe.utils.validate_email_address(email):
                    frappe.throw(f"Invalid email address: {email}")
                    
    def validate_stock_requisition_time(self):
        """Ensure stock requisition time is set properly"""
        if not self.stock_requisition_time:
            self.stock_requisition_time = "08:00:00"
            
    def on_update(self):
        """Update scheduler event if stock requisition time changes"""
        try:
            if not frappe.db.exists("DocType", "Medication Automation Settings"):
                return

            if not frappe.db.table_exists("tabMedication Automation Settings"):
                return
                
            old_time = frappe.db.get_value('Medication Automation Settings', 
                                         'Medication Automation Settings', 
                                         'stock_requisition_time')
            
            if old_time and old_time != self.stock_requisition_time:
                self.update_scheduler_event()
        except Exception as e:
            frappe.logger().error(f"Error in Medication Automation Settings on_update: {str(e)}")
                
    def update_scheduler_event(self):
        """Update the scheduler event timing"""
        try:
            # Get hour and minute from time
            hour = int(self.stock_requisition_time.split(':')[0])
            minute = int(self.stock_requisition_time.split(':')[1])
            
            # Update in hooks.py would be manual - this is just for logging
            frappe.logger().info(
                f"Stock requisition time changed to {hour:02d}:{minute:02d}. "
                "Please update hooks.py scheduler_events accordingly."
            )
        except Exception as e:
            frappe.logger().error(f"Error updating scheduler event: {str(e)}") 