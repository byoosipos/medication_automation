import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}
    
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Patient"), "fieldname": "patient", "fieldtype": "Link", "options": "Patient", "width": 120},
        {"label": _("Gender"), "fieldname": "gender", "fieldtype": "Data", "width": 90},
        {"label": _("Client Category"), "fieldname": "client_category", "fieldtype": "Data", "width": 120},
        {"label": _("Nationality"), "fieldname": "nationality", "fieldtype": "Data", "width": 100},
        {"label": _("Residence"), "fieldname": "residence", "fieldtype": "Data", "width": 120},
        {"label": _("Next of Kin"), "fieldname": "next_of_kin", "fieldtype": "Data", "width": 120},
        {"label": _("Nutrition Assessment"), "fieldname": "nutrition_note", "fieldtype": "Data", "width": 150},
        {"label": _("Blood Pressure"), "fieldname": "blood_pressure", "fieldtype": "Data", "width": 120},
        {"label": _("Tobacco Use"), "fieldname": "tobacco_use", "fieldtype": "Data", "width": 100},
        {"label": _("Alcohol Use"), "fieldname": "alcohol_use", "fieldtype": "Data", "width": 100},
        {"label": _("Lab Test"), "fieldname": "lab_test", "fieldtype": "Data", "width": 150},
        {"label": _("Attendance"), "fieldname": "attendance", "fieldtype": "Data", "width": 100},
        {"label": _("Diagnosis"), "fieldname": "diagnosis", "fieldtype": "Data", "width": 150},
        {"label": _("Drug Prescription"), "fieldname": "drug_prescription", "fieldtype": "Data", "width": 200}
    ]

def get_data(filters):
    conditions = get_conditions(filters)
    data = []
    
    # Get patient encounters within the date range
    encounters = frappe.get_all("Patient Encounter",
        filters=conditions,
        fields=["patient", "diagnosis", "drug_prescription", "creation"],
        order_by="creation desc"
    )
    
    # Get unique patients from encounters
    patient_list = list(set([enc.patient for enc in encounters]))
    
    for patient_name in patient_list:
        patient = frappe.get_doc("Patient", patient_name)
        
        # Get vital signs
        vital_signs = frappe.get_all("Vital Signs",
            filters={
                "patient": patient_name,
                "creation": ["between", [filters.get("from_date"), filters.get("to_date")]]
            },
            fields=["nutrition_note", "bp_systolic"],
            order_by="creation desc",
            limit=1
        )

        # Get patient history
        patient_history = frappe.get_all("Patient History",
            filters={"patient": patient_name},
            fields=["tobacco_current_use", "alcohol_current_use"],
            limit=1
        )

        # Get lab tests
        lab_tests = frappe.get_all("Lab Test",
            filters={
                "patient": patient_name,
                "creation": ["between", [filters.get("from_date"), filters.get("to_date")]]
            },
            fields=["test_name"],
            order_by="creation desc"
        )

        # Get latest encounter for this patient
        patient_encounters = [e for e in encounters if e.patient == patient_name]
        latest_encounter = patient_encounters[0] if patient_encounters else None

        row = {
            "patient": patient_name,
            "gender": patient.get("gender"),
            "client_category": patient.get("client_category"),
            "nationality": patient.get("nationality"),
            "residence": patient.get("custom_patient_residence"),
            "next_of_kin": patient.get("custom_full_name_kin"),
            "nutrition_note": vital_signs[0].nutrition_note if vital_signs else "",
            "blood_pressure": vital_signs[0].bp_systolic if vital_signs else "",
            "tobacco_use": patient_history[0].tobacco_current_use if patient_history else "",
            "alcohol_use": patient_history[0].alcohol_current_use if patient_history else "",
            "lab_test": ", ".join([lt.test_name for lt in lab_tests]) if lab_tests else "",
            "attendance": patient.get("custom_attendance_"),
            "diagnosis": latest_encounter.diagnosis if latest_encounter else "",
            "drug_prescription": latest_encounter.drug_prescription if latest_encounter else ""
        }
        data.append(row)

    return data

def get_conditions(filters):
    conditions = {}
    if filters.get("from_date"):
        conditions["creation"] = [">=", filters.get("from_date")]
    if filters.get("to_date"):
        conditions["creation"] = ["<=", filters.get("to_date")]
    if filters.get("from_date") and filters.get("to_date"):
        conditions["creation"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
    
    return conditions 