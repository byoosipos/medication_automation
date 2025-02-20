import frappe
from frappe.model.document import Document
from frappe.utils import getdate, flt, add_days

class InsuranceCoverage(Document):
    def validate(self):
        self.validate_dates()
        self.validate_coverage()
        self.validate_items()
        self.set_remaining_coverage()
        
    def validate_dates(self):
        """Validate coverage dates"""
        if getdate(self.coverage_start_date) > getdate(self.coverage_end_date):
            frappe.throw("Coverage End Date cannot be before Start Date")
            
        # Set status based on dates
        today = getdate()
        if today < getdate(self.coverage_start_date):
            self.status = "Pending"
        elif today > getdate(self.coverage_end_date):
            self.status = "Expired"
            
    def validate_coverage(self):
        """Validate coverage details"""
        if self.coverage_type == "Full" and flt(self.coverage_limit) <= 0:
            frappe.throw("Coverage Limit must be greater than zero for Full coverage")
            
        if self.coverage_type == "Co-Pay":
            if not self.patient_copay_percent:
                frappe.throw("Patient Co-pay Percentage is required for Co-Pay coverage type")
                
            if flt(self.patient_copay_percent) <= 0:
                frappe.throw("Patient Co-pay Percentage must be greater than zero")
                
            if flt(self.patient_copay_percent) >= 100:
                frappe.throw("Patient Co-pay Percentage must be less than 100%")
                
            # Validate at least one item has coverage less than 100%
            has_copay = False
            for item in self.covered_items:
                if flt(item.coverage_percentage) < 100:
                    has_copay = True
                    break
            if not has_copay:
                frappe.throw("Co-Pay coverage must have at least one item with coverage percentage less than 100%")
                
        if self.patient_deductible and flt(self.patient_deductible) > 0:
            if not self.deductible_remaining:
                self.deductible_remaining = self.patient_deductible
                
        if self.max_out_of_pocket and flt(self.max_out_of_pocket) <= 0:
            frappe.throw("Maximum Out of Pocket must be greater than zero")
            
    def validate_items(self):
        """Validate covered items"""
        if not self.covered_items:
            frappe.throw("At least one covered item must be specified")
            
        seen_groups = set()
        for item in self.covered_items:
            if item.item_group in seen_groups:
                frappe.throw(f"Duplicate Item Group {item.item_group} not allowed")
            seen_groups.add(item.item_group)
            
            # Convert percentage to float for comparison
            coverage_percentage = flt(item.coverage_percentage)
            if coverage_percentage <= 0:
                frappe.throw(f"Coverage Percentage must be greater than zero for {item.item_group}")
                
            if coverage_percentage > 100:
                frappe.throw(f"Coverage Percentage cannot exceed 100% for {item.item_group}")
                
            if item.max_amount and flt(item.max_amount) <= 0:
                frappe.throw(f"Maximum Amount must be greater than zero for {item.item_group}")
                
    def set_remaining_coverage(self):
        """Calculate and set remaining coverage"""
        if not self.coverage_limit:
            return
            
        # Get total claimed amount
        claimed_amount = frappe.db.sql("""
            SELECT IFNULL(SUM(total_amount), 0)
            FROM `tabInsurance Claim`
            WHERE insurance_coverage = %s
            AND docstatus = 1
        """, self.name)[0][0]
        
        self.remaining_coverage = flt(self.coverage_limit) - flt(claimed_amount)
        
    def on_submit(self):
        """Create insurance card on submit"""
        self.create_insurance_card()
        
    def create_insurance_card(self):
        """Create or update insurance card for patient"""
        existing_card = frappe.db.exists("Insurance Card", {
            "patient": self.patient,
            "insurance_company": self.insurance_company
        })
        
        card_data = {
            "patient": self.patient,
            "insurance_company": self.insurance_company,
            "policy_number": self.policy_number,
            "valid_from": self.coverage_start_date,
            "valid_till": self.coverage_end_date,
            "coverage_type": self.coverage_type,
            "copay_percent": self.patient_copay_percent,
            "deductible": self.patient_deductible
        }
        
        if existing_card:
            card = frappe.get_doc("Insurance Card", existing_card)
            card.update(card_data)
            card.save()
        else:
            card = frappe.get_doc({
                "doctype": "Insurance Card",
                **card_data
            })
            card.insert()
            
    def check_item_coverage(self, item_code, amount):
        """
        Check coverage for a specific item
        Returns dict with coverage details
        """
        if self.status != "Active":
            return {"covered": False, "reason": f"Insurance coverage is {self.status}"}
            
        # Get item group
        item_group = frappe.db.get_value("Item", item_code, "item_group")
        if not item_group:
            return {"covered": False, "reason": "Item group not found"}
            
        # Find coverage for item group
        coverage = None
        for item in self.covered_items:
            if item.item_group == item_group:
                coverage = item
                break
                
        if not coverage:
            return {"covered": False, "reason": f"Item group {item_group} not covered"}
            
        # Check if approval is required
        if coverage.approval_required:
            if self.requires_preapproval:
                if flt(amount) <= flt(self.auto_approval_limit):
                    approval_status = "Auto-Approved"
                else:
                    approval_status = self.default_approval_status
            else:
                approval_status = "Approved"
        else:
            approval_status = "Not Required"
            
        # Calculate covered amount
        covered_amount = flt(amount) * flt(coverage.coverage_percentage) / 100
        if coverage.max_amount:
            covered_amount = min(covered_amount, flt(coverage.max_amount))
            
        # Check remaining coverage
        if self.remaining_coverage and covered_amount > self.remaining_coverage:
            covered_amount = self.remaining_coverage
            
        return {
            "covered": True,
            "coverage_percentage": coverage.coverage_percentage,
            "covered_amount": covered_amount,
            "patient_amount": flt(amount) - covered_amount,
            "approval_required": coverage.approval_required,
            "approval_status": approval_status,
            "approval_validity": add_days(getdate(), self.approval_validity_days) if self.approval_validity_days else None
        }
        
    def create_claim(self, items, diagnosis=None, practitioner=None):
        """
        Create insurance claim for items
        items: list of dicts with item_code and amount
        """
        if self.status != "Active":
            frappe.throw(f"Cannot create claim for {self.status} insurance coverage")
            
        claim = frappe.get_doc({
            "doctype": "Insurance Claim",
            "insurance_coverage": self.name,
            "patient": self.patient,
            "insurance_company": self.insurance_company,
            "claim_date": getdate(),
            "diagnosis": diagnosis,
            "practitioner": practitioner,
            "items": []
        })
        
        total_amount = 0
        total_covered = 0
        
        for item in items:
            coverage = self.check_item_coverage(item["item_code"], item["amount"])
            if not coverage["covered"]:
                continue
                
            claim.append("items", {
                "item_code": item["item_code"],
                "amount": item["amount"],
                "coverage_percentage": coverage["coverage_percentage"],
                "covered_amount": coverage["covered_amount"],
                "patient_amount": coverage["patient_amount"],
                "approval_required": coverage["approval_required"],
                "approval_status": coverage["approval_status"],
                "approval_validity": coverage["approval_validity"]
            })
            
            total_amount += flt(item["amount"])
            total_covered += flt(coverage["covered_amount"])
            
        if not claim.items:
            frappe.throw("No covered items found to create claim")
            
        claim.total_amount = total_amount
        claim.total_covered_amount = total_covered
        claim.total_patient_amount = total_amount - total_covered
        
        claim.insert()
        return claim.name

    @frappe.whitelist()
    def update_deductible(self, amount):
        """Update deductible remaining amount"""
        try:
            frappe.logger().debug(f"Updating deductible for coverage {self.name}")
            
            amount = flt(amount)
            current_remaining = flt(self.deductible_remaining)
            
            frappe.logger().debug(f"Current remaining: {current_remaining}, Amount to deduct: {amount}")
            
            if amount > 0:  # Deduction
                if amount > current_remaining:
                    msg = f"Deductible amount {amount} exceeds remaining {current_remaining}"
                    frappe.logger().error(msg)
                    frappe.throw(msg)
                new_remaining = current_remaining - amount
            else:  # Reversal
                if abs(amount) > flt(self.patient_deductible - current_remaining):
                    msg = f"Reversal amount {abs(amount)} exceeds applied deductible {self.patient_deductible - current_remaining}"
                    frappe.logger().error(msg)
                    frappe.throw(msg)
                new_remaining = current_remaining - amount  # Subtract negative amount = add
                
            frappe.logger().debug(f"New remaining deductible: {new_remaining}")
            
            # Update using direct SQL to bypass document validation
            frappe.db.sql("""
                UPDATE `tabInsurance Coverage`
                SET deductible_remaining = %s
                WHERE name = %s
            """, (new_remaining, self.name))
            
            frappe.db.commit()
            
            # Reload the document to reflect changes
            self.reload()
            
            frappe.logger().debug(f"Deductible update completed successfully")
            
            return new_remaining
            
        except Exception as e:
            frappe.logger().error(f"Deductible update failed: {str(e)}")
            error_msg = f"Failed to update deductible: {str(e)}"
            if len(error_msg) > 140:
                error_msg = error_msg[:137] + "..."
            frappe.log_error(
                message=error_msg,
                title="Insurance Coverage Error"
            )
            raise 