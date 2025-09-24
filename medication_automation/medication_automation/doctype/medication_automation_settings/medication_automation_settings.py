import frappe
from frappe.model.document import Document
from frappe.utils import get_time, time_diff_in_hours

class MedicationAutomationSettings(Document):
    def validate(self):
        self.validate_email_list()
        self.validate_stock_requisition_time()
        # Temporarily disabled shift time validations
        # self.validate_shift_times()
        
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
            
    def validate_shift_times(self):
        """Validate shift time configurations"""
        # Temporarily disabled shift time validations
        return
        
        # The following code is temporarily disabled
        '''
        # Convert times to datetime.time objects for comparison
        first_start = get_time(self.first_shift_start)
        first_end = get_time(self.first_shift_end)
        second_start = get_time(self.second_shift_start)
        second_end = get_time(self.second_shift_end)
        
        # Validate first shift
        if first_start >= first_end:
            frappe.throw("First shift end time must be after start time")
            
        # Calculate shift durations
        first_duration = time_diff_in_hours(
            f"2000-01-01 {self.first_shift_end}",
            f"2000-01-01 {self.first_shift_start}"
        )
        
        # For second shift, handle overnight case
        if self.second_shift_crosses_midnight:
            if not self.second_shift_next_day_end:
                frappe.throw("Please specify the hour when second shift ends on next day")
                
            if self.second_shift_next_day_end < 0 or self.second_shift_next_day_end > 12:
                frappe.throw("Next day end hour must be between 0 and 12")
                
            # Calculate duration considering overnight
            second_duration = time_diff_in_hours(
                f"2000-01-02 {self.second_shift_end}",
                f"2000-01-01 {self.second_shift_start}"
            )
        else:
            # Normal duration calculation for same-day shift
            if second_start >= second_end:
                frappe.throw("Second shift end time must be after start time")
                
            second_duration = time_diff_in_hours(
                f"2000-01-01 {self.second_shift_end}",
                f"2000-01-01 {self.second_shift_start}"
            )
            
        # Validate shift durations based on settings
        if self.allow_flexible_duration:
            # Check if durations match configured values
            if abs(first_duration - self.first_shift_duration) > 0.1:
                frappe.throw(f"First shift duration must be {self.first_shift_duration} hours")
            if abs(second_duration - self.second_shift_duration) > 0.1:
                frappe.throw(f"Second shift duration must be {self.second_shift_duration} hours")
                
            # Validate total coverage (should be 24 hours)
            if abs(first_duration + second_duration - 24) > 0.1:
                frappe.throw("Total shift coverage must be 24 hours")
        else:
            # Default 12-hour shifts
            if abs(first_duration - 12) > 0.1 or abs(second_duration - 12) > 0.1:
                frappe.throw("Each shift must be exactly 12 hours long when flexible duration is disabled")
            
        # Validate shift alignment
        if first_end != second_start:
            frappe.throw("First shift end time must match second shift start time")
            
        # For overnight shifts, validate next day start aligns with first shift
        if self.second_shift_crosses_midnight:
            if second_end != first_start:
                frappe.throw("Second shift end time must match first shift start time on next day")
        '''
            
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