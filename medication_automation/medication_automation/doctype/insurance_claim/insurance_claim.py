import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, get_datetime, add_to_date

class InsuranceClaim(Document):
    def validate(self):
        self.validate_coverage()
        if not self.items:  # Only fetch if no items exist
            self.fetch_billable_items()
        self.validate_items()
        self.calculate_totals()
        self.set_claim_status()
        
    def validate_coverage(self):
        """Validate insurance coverage"""
        coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
        
        if coverage.status != "Active":
            frappe.throw(f"Insurance coverage {self.insurance_coverage} is {coverage.status}")
            
        if coverage.patient != self.patient:
            frappe.throw("Patient in claim does not match insurance coverage")
            
        if coverage.insurance_company != self.insurance_company:
            frappe.throw("Insurance company in claim does not match coverage")
            
        # Store coverage details for calculations
        self.patient_copay_percent = coverage.patient_copay_percent
        self.patient_deductible = coverage.patient_deductible
        self.deductible_remaining = coverage.deductible_remaining
        self.max_out_of_pocket = coverage.max_out_of_pocket
            
    def fetch_billable_items(self):
        """Fetch all billable items from various healthcare services"""
        self.fetch_medication_entries()
        self.fetch_lab_tests()
        self.fetch_clinical_procedures()
        self.fetch_therapy_sessions()
        self.fetch_inpatient_services()

    def fetch_medication_entries(self):
        """Fetch medication entries for the claim period"""
        if not self.claim_date:
            self.claim_date = getdate()
            
        # Get medication entries for the claim date
        entries = frappe.get_all(
            "Inpatient Medication Entry",
            filters={
                "patient": self.patient,
                "posting_date": self.claim_date,
                "docstatus": 1,  # Submitted
                "custom_insurance_claimed": 0  # Not yet claimed
            },
            fields=["name", "patient", "service_unit", "posting_date"]
        )
        
        for entry in entries:
            # Get medication details
            medications = frappe.get_all(
                "Inpatient Medication Entry Detail",
                filters={"parent": entry.name},
                fields=["drug_code", "drug_name", "dosage", "dosage_form"]
            )
            
            for med in medications:
                # Get item group for coverage check
                item_group = frappe.db.get_value("Item", med.drug_code, "item_group")
                
                # Check if item group is covered
                coverage = None
                for item in frappe.get_doc("Insurance Coverage", self.insurance_coverage).covered_items:
                    if item.item_group == item_group:
                        coverage = item
                        break
                        
                if not coverage:
                    continue  # Skip if not covered
                    
                # Calculate amount based on dosage and rate
                rate = frappe.db.get_value("Item", med.drug_code, "standard_rate") or 0
                amount = flt(med.dosage) * flt(rate)
                
                # Add to claim items
                self.append("items", {
                    "item_code": med.drug_code,
                    "item_name": med.drug_name,
                    "amount": amount,
                    "medication_entry": entry.name,
                    "service_unit": entry.service_unit,
                    "dosage": med.dosage,
                    "dosage_form": med.dosage_form
                })
                
    def fetch_lab_tests(self):
        """Fetch unclaimed lab tests"""
        lab_tests = frappe.get_all(
            "Lab Test",
            filters={
                "patient": self.patient,
                "docstatus": 1,  # Submitted
                "insurance_claim": ["in", ["", None]],  # Not claimed
                "creation": ["between", [
                    f"{self.claim_date} 00:00:00",
                    f"{self.claim_date} 23:59:59"
                ]]
            },
            fields=["name", "template", "patient", "practitioner", "department"]
        )
        
        for test in lab_tests:
            template = frappe.get_doc("Lab Test Template", test.template)
            
            # Check if template's item group is covered
            coverage = None
            for item in frappe.get_doc("Insurance Coverage", self.insurance_coverage).covered_items:
                if item.item_group == template.item_group:
                    coverage = item
                    break
                    
            if not coverage:
                continue  # Skip if not covered
                
            # Add to claim items
            self.append("items", {
                "item_code": template.item,
                "item_name": template.lab_test_name,
                "amount": template.lab_test_rate,
                "reference_dt": "Lab Test",
                "reference_dn": test.name,
                "practitioner": test.practitioner,
                "department": test.department
            })

    def fetch_clinical_procedures(self):
        """Fetch unclaimed clinical procedures"""
        procedures = frappe.get_all(
            "Clinical Procedure",
            filters={
                "patient": self.patient,
                "docstatus": 1,  # Submitted
                "insurance_claim": ["in", ["", None]],  # Not claimed
                "creation": ["between", [
                    f"{self.claim_date} 00:00:00",
                    f"{self.claim_date} 23:59:59"
                ]]
            },
            fields=["name", "procedure_template", "patient", "practitioner", "service_unit"]
        )
        
        for procedure in procedures:
            template = frappe.get_doc("Clinical Procedure Template", procedure.procedure_template)
            
            # Check if template's item group is covered
            coverage = None
            for item in frappe.get_doc("Insurance Coverage", self.insurance_coverage).covered_items:
                if item.item_group == template.item_group:
                    coverage = item
                    break
                    
            if not coverage:
                continue  # Skip if not covered
                
            # Add to claim items
            self.append("items", {
                "item_code": template.item,
                "item_name": template.procedure_name,
                "amount": template.procedure_rate,
                "reference_dt": "Clinical Procedure",
                "reference_dn": procedure.name,
                "practitioner": procedure.practitioner,
                "service_unit": procedure.service_unit
            })

    def fetch_therapy_sessions(self):
        """Fetch unclaimed therapy sessions"""
        sessions = frappe.get_all(
            "Therapy Session",
            filters={
                "patient": self.patient,
                "docstatus": 1,  # Submitted
                "insurance_claim": ["in", ["", None]],  # Not claimed
                "creation": ["between", [
                    f"{self.claim_date} 00:00:00",
                    f"{self.claim_date} 23:59:59"
                ]]
            },
            fields=["name", "therapy_type", "patient", "practitioner", "department"]
        )
        
        for session in sessions:
            therapy_type = frappe.get_doc("Therapy Type", session.therapy_type)
            
            # Check if therapy's item group is covered
            coverage = None
            for item in frappe.get_doc("Insurance Coverage", self.insurance_coverage).covered_items:
                if item.item_group == therapy_type.item_group:
                    coverage = item
                    break
                    
            if not coverage:
                continue  # Skip if not covered
                
            # Add to claim items
            self.append("items", {
                "item_code": therapy_type.item,
                "item_name": therapy_type.therapy_type,
                "amount": therapy_type.rate,
                "reference_dt": "Therapy Session",
                "reference_dn": session.name,
                "practitioner": session.practitioner,
                "department": session.department
            })

    def fetch_inpatient_services(self):
        """Fetch unclaimed inpatient services"""
        if not self.admission_id:
            return
            
        services = frappe.get_all(
            "Inpatient Occupancy",
            filters={
                "parent": self.admission_id,
                "insurance_claim": ["in", ["", None]],  # Not claimed
                "date": self.claim_date
            },
            fields=["name", "service_unit", "check_in", "check_out"]
        )
        
        for service in services:
            service_unit = frappe.get_doc("Healthcare Service Unit", service.service_unit)
            if not service_unit.is_billable:
                continue
                
            # Check if service unit's item group is covered
            coverage = None
            for item in frappe.get_doc("Insurance Coverage", self.insurance_coverage).covered_items:
                if item.item_group == service_unit.item_group:
                    coverage = item
                    break
                    
            if not coverage:
                continue  # Skip if not covered
                
            # Calculate duration and amount
            duration = time_diff_in_hours(service.check_out, service.check_in)
            rate = service_unit.service_unit_rate or 0
            amount = duration * rate
                
            # Add to claim items
            self.append("items", {
                "item_code": service_unit.item,
                "item_name": f"Room Charges - {service_unit.service_unit_name}",
                "amount": amount,
                "reference_dt": "Inpatient Occupancy",
                "reference_dn": service.name,
                "service_unit": service.service_unit
            })
                
    def validate_items(self):
        """Validate claim items"""
        if not self.items:
            frappe.throw("No claimable items found for the selected date")
            
        coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
        remaining_deductible = flt(self.deductible_remaining)
        
        for item in self.items:
            # Get item group
            item_group = frappe.db.get_value("Item", item.item_code, "item_group")
            if not item_group:
                frappe.throw(f"Item group not found for {item.item_code}")
                
            # Find coverage for item group
            item_coverage = None
            for covered_item in coverage.covered_items:
                if covered_item.item_group == item_group:
                    item_coverage = covered_item
                    break
                    
            if not item_coverage:
                frappe.throw(f"Item group {item_group} not covered by insurance")
                
            # Calculate patient portion first (deductible)
            deductible_applied = min(remaining_deductible, item.amount)
            remaining_deductible -= deductible_applied  # Update remaining deductible for next item
            remaining_amount = item.amount - deductible_applied
            
            # Calculate insurance and patient portions
            insurance_portion = flt(remaining_amount) * (1 - flt(self.patient_copay_percent) / 100)
            patient_portion = remaining_amount - insurance_portion + deductible_applied
            
            # Apply maximum amount if specified
            if item_coverage.max_amount and insurance_portion > item_coverage.max_amount:
                excess = insurance_portion - item_coverage.max_amount
                insurance_portion = item_coverage.max_amount
                patient_portion += excess
                
            # Update item amounts
            item.deductible_applied = deductible_applied
            item.insurance_amount = insurance_portion
            item.patient_amount = patient_portion
            
            # Set approval details
            item.approval_required = item_coverage.approval_required
            if item.approval_required:
                if coverage.requires_preapproval:
                    if flt(item.amount) <= flt(coverage.auto_approval_limit):
                        item.approval_status = "Auto-Approved"
                    else:
                        item.approval_status = coverage.default_approval_status
                        
                    if coverage.approval_validity_days:
                        item.approval_validity = add_to_date(
                            getdate(), 
                            days=coverage.approval_validity_days
                        )
                else:
                    item.approval_status = "Approved"
                    
    def calculate_totals(self):
        """Calculate claim totals"""
        self.total_amount = sum(flt(item.amount) for item in self.items)
        self.total_deductible = sum(flt(item.deductible_applied) for item in self.items)
        self.total_insurance_amount = sum(flt(item.insurance_amount) for item in self.items)
        self.total_patient_amount = sum(flt(item.patient_amount) for item in self.items)
        
    def set_claim_status(self):
        """Set overall claim status based on items"""
        if not self.items:
            self.claim_status = "Pending"
            return
            
        # Check if any items need approval
        pending_approval = any(
            item.approval_required and item.approval_status in ["Pending", None]
            for item in self.items
        )
        
        if pending_approval:
            self.claim_status = "Pending"
            return
            
        # Check if any items are rejected
        has_rejected = any(
            item.approval_required and item.approval_status == "Rejected"
            for item in self.items
        )
        
        if has_rejected:
            if len(self.items) == 1:
                self.claim_status = "Rejected"
            else:
                self.claim_status = "Partially Approved"
            return
            
        # All items are approved
        self.claim_status = "Approved"
        
    def before_submit(self):
        """Create sales invoices before claim submission"""
        try:
            if self.claim_status not in ["Approved", "Partially Approved"]:
                frappe.throw("Cannot submit claim that is not approved")
            
            # Update deductible in Insurance Coverage
            if self.insurance_coverage and self.total_deductible:
                try:
                    frappe.logger().debug(f"Creating deductible update for claim {self.name}")
                    
                    # Create a Deductible Update record
                    deductible_update = frappe.get_doc({
                        "doctype": "Insurance Deductible Update",
                        "insurance_coverage": self.insurance_coverage,
                        "insurance_claim": self.name,
                        "deductible_amount": self.total_deductible,
                        "posting_date": self.claim_date
                    })
                    deductible_update.insert()
                    
                    frappe.logger().debug(f"Updating deductible in coverage {self.insurance_coverage}")
                    
                    # Update the deductible remaining in coverage
                    coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
                    if coverage.docstatus == 1:  # If submitted
                        # Use update_deductible method which will handle the workflow
                        coverage.update_deductible(self.total_deductible)
                        frappe.logger().debug(f"Deductible updated successfully")
                    
                    # Submit the deductible update
                    deductible_update.submit()
                    frappe.logger().debug(f"Deductible update submitted successfully")
                    
                except Exception as e:
                    frappe.logger().error(f"Deductible update failed: {str(e)}")
                    error_msg = f"Deductible update failed: {str(e)}"
                    if len(error_msg) > 140:
                        error_msg = error_msg[:137] + "..."
                    frappe.log_error(
                        message=error_msg,
                        title="Insurance Claim Error"
                    )
                    frappe.throw("Failed to update insurance deductible. Please check error logs.")
            
            frappe.logger().debug(f"Creating sales invoices for claim {self.name}")
            self.create_sales_invoices()
            
        except Exception as e:
            frappe.logger().error(f"Claim submission preparation failed: {str(e)}")
            error_msg = f"Claim submission preparation failed: {str(e)}"
            if len(error_msg) > 140:
                error_msg = error_msg[:137] + "..."
            frappe.log_error(
                message=error_msg,
                title="Insurance Claim Error"
            )
            frappe.throw("Failed to prepare insurance claim for submission. Please check error logs.")

    def on_submit(self):
        """Update medication entries after successful submission"""
        try:
            # Verify that sales invoices exist and are submitted
            invoices = frappe.db.sql("""
                SELECT DISTINCT parent 
                FROM `tabSales Invoice Item`
                WHERE reference_dt = 'Insurance Claim'
                AND reference_dn = %s
                AND docstatus = 1
            """, self.name, as_dict=1)
            
            if not invoices:
                frappe.throw("Cannot submit claim without submitted sales invoices")
            
            frappe.logger().debug(f"Updating medication entries for claim {self.name}")
            self.update_medication_entries()
            
            frappe.logger().debug(f"Claim {self.name} submitted successfully")
            
        except Exception as e:
            frappe.logger().error(f"Claim submission failed: {str(e)}")
            error_msg = f"Claim submission failed: {str(e)}"
            if len(error_msg) > 140:
                error_msg = error_msg[:137] + "..."
            frappe.log_error(
                message=error_msg,
                title="Insurance Claim Error"
            )
            frappe.throw("Failed to submit insurance claim. Please check error logs.")
        
    def update_medication_entries(self):
        """Mark medication entries as claimed"""
        medication_entries = set(item.medication_entry for item in self.items)
        for entry_name in medication_entries:
            frappe.db.set_value(
                "Inpatient Medication Entry",
                entry_name,
                "custom_insurance_claimed",
                1
            )
            
    def create_sales_invoices(self):
        """Create separate sales invoices for insurance and patient portions"""
        # Get customer details
        coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
        patient_customer = coverage.patient_customer
        if not patient_customer:
            frappe.throw(f"No customer account linked to patient {self.patient}")
            
        insurance_customer = frappe.db.get_value("Insurance Company", 
                                               self.insurance_company, 
                                               "customer")
        if not insurance_customer:
            frappe.throw(f"No customer account linked to insurance company {self.insurance_company}")
            
        # Create insurance portion invoice
        if self.total_insurance_amount > 0:
            insurance_invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": insurance_customer,
                "due_date": self.claim_date,
                "insurance_claim": self.name,
                "items": []
            })
            
            # Add items with insurance portion
            for item in self.items:
                if flt(item.insurance_amount) > 0:
                    description = f"{item.item_name}"
                    if hasattr(item, 'dosage') and item.dosage:
                        description += f"\nDosage: {item.dosage}"
                    if hasattr(item, 'dosage_form') and item.dosage_form:
                        description += f" {item.dosage_form}"
                    if hasattr(item, 'medication_entry') and item.medication_entry:
                        description += f"\nRef: Medication Entry {item.medication_entry}"
                        
                    insurance_invoice.append("items", {
                        "item_code": item.item_code,
                        "qty": getattr(item, 'dosage', 1) or 1,
                        "rate": flt(item.insurance_amount) / flt(getattr(item, 'dosage', 1) or 1),
                        "amount": item.insurance_amount,
                        "reference_dt": "Insurance Claim",
                        "reference_dn": self.name,
                        "description": description
                    })
                    
            insurance_invoice.insert()
            insurance_invoice.submit()
            
        # Create patient portion invoice
        if self.total_patient_amount > 0:
            patient_invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": patient_customer,
                "due_date": self.claim_date,
                "insurance_claim": self.name,
                "items": []
            })
            
            # Add items with patient portion
            for item in self.items:
                if flt(item.patient_amount) > 0:
                    description = f"{item.item_name}"
                    if hasattr(item, 'dosage') and item.dosage:
                        description += f"\nDosage: {item.dosage}"
                    if hasattr(item, 'dosage_form') and item.dosage_form:
                        description += f" {item.dosage_form}"
                    if hasattr(item, 'deductible_applied') and item.deductible_applied:
                        description += f"\nDeductible Applied: {item.deductible_applied}"
                    if flt(item.patient_amount - item.deductible_applied) > 0:
                        description += f"\nCo-pay Amount: {item.patient_amount - item.deductible_applied}"
                    if hasattr(item, 'medication_entry') and item.medication_entry:
                        description += f"\nRef: Medication Entry {item.medication_entry}"
                        
                    patient_invoice.append("items", {
                        "item_code": item.item_code,
                        "qty": getattr(item, 'dosage', 1) or 1,
                        "rate": flt(item.patient_amount) / flt(getattr(item, 'dosage', 1) or 1),
                        "amount": item.patient_amount,
                        "description": description,
                        "reference_dt": "Insurance Claim",
                        "reference_dn": self.name
                    })
                    
            patient_invoice.insert()
            patient_invoice.submit()
            
    def on_cancel(self):
        """Cancel linked sales invoices and update medication entries"""
        # Reload the document to ensure we have all fields
        self.reload()
        
        # Get total deductible from items if not available directly
        total_deductible = 0
        if hasattr(self, 'total_deductible'):
            total_deductible = self.total_deductible
        else:
            total_deductible = sum(flt(item.deductible_applied) for item in self.items)

        # Revert deductible update
        if self.insurance_coverage and total_deductible:
            try:
                # Find and cancel deductible update
                deductible_updates = frappe.get_all(
                    "Insurance Deductible Update",
                    filters={
                        "insurance_claim": self.name,
                        "docstatus": 1
                    }
                )
                
                for update in deductible_updates:
                    update_doc = frappe.get_doc("Insurance Deductible Update", update.name)
                    update_doc.cancel()
                
                # Revert the deductible in coverage
                coverage = frappe.get_doc("Insurance Coverage", self.insurance_coverage)
                if coverage.docstatus == 1:  # If submitted
                    # Use update_deductible method with negative amount to revert
                    coverage.update_deductible(-1 * total_deductible)
                
            except Exception as e:
                frappe.log_error(
                    message=f"Deductible revert failed for claim {self.name}: {str(e)}",
                    title="Insurance Claim Error"
                )
                frappe.throw("Failed to revert insurance deductible. Please contact system administrator.")
        
        # Cancel invoices - using direct SQL query to find linked invoices
        invoices = frappe.db.sql("""
            SELECT DISTINCT parent 
            FROM `tabSales Invoice Item`
            WHERE reference_dt = 'Insurance Claim'
            AND reference_dn = %s
            AND docstatus = 1
        """, self.name, as_dict=1)
        
        for invoice in invoices:
            inv_doc = frappe.get_doc("Sales Invoice", invoice.parent)
            inv_doc.cancel()
            
        # Unmark medication entries
        medication_entries = set(item.medication_entry for item in self.items if item.medication_entry)
        for entry_name in medication_entries:
            frappe.db.set_value(
                "Inpatient Medication Entry",
                entry_name,
                "custom_insurance_claimed",
                0
            ) 