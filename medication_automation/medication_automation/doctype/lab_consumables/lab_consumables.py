# Copyright (c) 2025, Byoosi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LabConsumables(Document):
	def validate(self):
		self.set_warehouse_based_on_parent()

	def set_warehouse_based_on_parent(self):
		if not self.warehouse:
			parent_doctype = self.parenttype
			
			if parent_doctype == "Lab Test":
				default_warehouse = frappe.db.get_single_value("Medication Automation Settings", "laboratory_warehouse")
				if default_warehouse:
					self.warehouse = default_warehouse
				
			elif parent_doctype == "Observation":
				default_warehouse = frappe.db.get_single_value("Medication Automation Settings", "radiology_warehouse")
				if default_warehouse:
					self.warehouse = default_warehouse

@frappe.whitelist()
def get_default_warehouse(doctype):
	"""Get default warehouse based on doctype from settings"""
	if doctype == "Lab Test":
		return frappe.db.get_single_value("Medication Automation Settings", "laboratory_warehouse")
	elif doctype == "Observation":
		return frappe.db.get_single_value("Medication Automation Settings", "radiology_warehouse")
	return None
