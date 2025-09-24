import frappe
from frappe import _
from healthcare.healthcare.doctype.healthcare_settings.healthcare_settings import get_income_account


def create_sales_invoice_for_clinical_procedure(doc, method=None):
    """
    Create Sales Invoice for Clinical Procedure on completion
    """
    if not doc.company or doc.docstatus != 1 or doc.status != "Completed":
        return

    # Check if patient is linked to a customer
    customer = frappe.db.get_value("Patient", doc.patient, "customer")
    if not customer:
        frappe.throw(_("Please link the Patient {0} to a Customer before completing the Clinical Procedure").format(
            frappe.bold(doc.patient)), title=_("Customer Not Found"))

    # Get the service item for clinical procedure
    service_item, practitioner_charge = get_service_item_and_practitioner_charge(doc)
    if not service_item:
        service_item = get_healthcare_service_item(doc.company)
        if not service_item:
            frappe.throw(_("Please configure Clinical Procedure Item in Healthcare Settings"))

    # Create sales invoice
    invoice = create_sales_invoice(doc, service_item, customer)
    
    # Link the sales invoice to the clinical procedure
    if invoice:
        doc.db_set('ref_sales_invoice', invoice.name)
        frappe.msgprint(_("Sales Invoice {0} created").format(
            frappe.get_desk_link("Sales Invoice", invoice.name)))

def create_sales_invoice(procedure, service_item, customer):
    """
    Create Sales Invoice for the Clinical Procedure
    """
    sales_invoice = frappe.new_doc("Sales Invoice")
    sales_invoice.patient = procedure.patient
    sales_invoice.customer = customer
    sales_invoice.company = procedure.company
    sales_invoice.due_date = frappe.utils.getdate()
    
    # Get income account
    income_account = get_income_account(procedure.practitioner, procedure.company)
    
    # Add the procedure item
    sales_invoice.append("items", {
        "item_code": service_item,
        "qty": 1,
        "reference_dt": "Clinical Procedure",
        "reference_dn": procedure.name,
        "income_account": income_account
    })

    # Add consumables if they are not to be billed separately
    if procedure.items and not procedure.invoice_separately_as_consumables:
        for item in procedure.items:
            sales_invoice.append("items", {
                "item_code": item.item_code,
                "qty": item.qty,
                "reference_dt": "Clinical Procedure",
                "reference_dn": procedure.name,
                "income_account": income_account
            })

    # Set other necessary fields
    sales_invoice.set_missing_values()
    sales_invoice.is_pos = 0
    sales_invoice.insert(ignore_permissions=True)
    
    return sales_invoice

def on_clinical_procedure_completed(doc, method=None):
    """
    Handler for Clinical Procedure completion
    """
    create_sales_invoice_for_clinical_procedure(doc)
