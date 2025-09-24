# Copyright (c) 2025, Byoosi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from datetime import datetime, timedelta


def execute(filters=None):
	if not filters:
		filters = {}
	
	# Get date range
	from_date = filters.get('from_date')
	to_date = filters.get('to_date')
	
	# Get facility
	facility = filters.get('facility')
	
	if not from_date:
		from_date = datetime.now().date().replace(day=1)  # First day of current month
	if not to_date:
		to_date = datetime.now().date()  # Today
	
	columns = get_columns()
	data = get_data(from_date, to_date, facility)
	
	return columns, data

def get_filters():
	return [
		{
			"fieldname": "from_date",
			"label": _("From Date"),
			"fieldtype": "Date",
			"default": datetime.now().date().replace(day=1),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": _("To Date"),
			"fieldtype": "Date",
			"default": datetime.now().date(),
			"reqd": 1
		},
		{
			"fieldname": "facility",
			"label": _("Facility"),
			"fieldtype": "Link",
			"options": "Medical Department"
		}
	]

def get_columns():
	return [
		{
			"label": _("Indicator"),
			"fieldname": "indicator",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": _("Value"),
			"fieldname": "value",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Percentage"),
			"fieldname": "percentage",
			"fieldtype": "Percent",
			"width": 150
		}
	]

def get_data(from_date, to_date, facility):
	data = []
	
	# 1. Outpatient Statistics
	outpatient_data = get_outpatient_stats(from_date, to_date, facility)
	data.extend(outpatient_data)
	
	# 2. Inpatient Statistics
	inpatient_data = get_inpatient_stats(from_date, to_date, facility)
	data.extend(inpatient_data)
	
	# 3. Maternal Health Statistics
	maternal_data = get_maternal_stats(from_date, to_date, facility)
	data.extend(maternal_data)
	
	# 4. Child Health Statistics
	child_data = get_child_stats(from_date, to_date, facility)
	data.extend(child_data)
	
	return data

def get_outpatient_stats(from_date, to_date, facility):
	data = []
	
	# Get total outpatient visits
	conditions = get_conditions(facility)
	total_visits = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Total Outpatient Visits",
		"value": total_visits,
		"percentage": 100
	})
	
	# Get new patients
	new_patients = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND patient NOT IN (
			SELECT DISTINCT patient 
			FROM `tabPatient Encounter`
			WHERE encounter_date < %s
		)
		{conditions}
	""".format(conditions=conditions), (from_date, to_date, from_date))[0][0]
	
	data.append({
		"indicator": "New Patients",
		"value": new_patients,
		"percentage": (new_patients / total_visits * 100) if total_visits else 0
	})
	
	# Get follow-up visits
	followup_visits = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND patient IN (
			SELECT DISTINCT patient 
			FROM `tabPatient Encounter`
			WHERE encounter_date < %s
		)
		{conditions}
	""".format(conditions=conditions), (from_date, to_date, from_date))[0][0]
	
	data.append({
		"indicator": "Follow-up Visits",
		"value": followup_visits,
		"percentage": (followup_visits / total_visits * 100) if total_visits else 0
	})
	
	# Get visits by gender
	male_visits = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND patient_sex = 'Male'
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Male Patients",
		"value": male_visits,
		"percentage": (male_visits / total_visits * 100) if total_visits else 0
	})
	
	female_visits = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND patient_sex = 'Female'
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Female Patients",
		"value": female_visits,
		"percentage": (female_visits / total_visits * 100) if total_visits else 0
	})
	
	return data

def get_inpatient_stats(from_date, to_date, facility):
	data = []
	
	# Get total admissions
	conditions = get_conditions(facility)
	total_admissions = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabInpatient Record`
		WHERE admitted_datetime BETWEEN %s AND %s
		AND status = 'Admitted'
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Total Inpatient Admissions",
		"value": total_admissions,
		"percentage": 100
	})
	
	# Get discharges
	total_discharges = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabInpatient Record`
		WHERE discharge_datetime BETWEEN %s AND %s
		AND status = 'Discharged'
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Total Discharges",
		"value": total_discharges,
		"percentage": (total_discharges / total_admissions * 100) if total_admissions else 0
	})
	
	# Get average length of stay
	avg_length_of_stay = frappe.db.sql("""
		SELECT AVG(TIMESTAMPDIFF(DAY, admitted_datetime, COALESCE(discharge_datetime, NOW())))
		FROM `tabInpatient Record`
		WHERE admitted_datetime BETWEEN %s AND %s
		AND status IN ('Admitted', 'Discharged')
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Average Length of Stay (Days)",
		"value": round(avg_length_of_stay, 1) if avg_length_of_stay else 0,
		"percentage": 0
	})
	
	# Get inpatient deaths
	inpatient_deaths = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabInpatient Record`
		WHERE admitted_datetime BETWEEN %s AND %s
		AND status = 'Discharged'
		AND discharge_note LIKE '%%Death%%'
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Inpatient Deaths",
		"value": inpatient_deaths,
		"percentage": (inpatient_deaths / total_admissions * 100) if total_admissions else 0
	})
	
	return data

def get_maternal_stats(from_date, to_date, facility):
	data = []
	
	# Get total maternal visits (female patients)
	conditions = get_conditions(facility)
	total_maternal_visits = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND patient_sex = 'Female'
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Total Maternal Visits",
		"value": total_maternal_visits,
		"percentage": 100
	})
	
	# Get total antenatal visits
	total_antenatal = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND patient_sex = 'Female'
		AND EXISTS (
			SELECT 1 FROM `tabPatient Encounter Diagnosis` ped
			WHERE ped.parent = `tabPatient Encounter`.name
			AND ped.diagnosis LIKE '%%Antenatal%%'
		)
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Total Antenatal Visits",
		"value": total_antenatal,
		"percentage": 100
	})
	
	return data

def get_child_stats(from_date, to_date, facility):
	data = []
	
	# Get total child visits (patients under 18 years)
	conditions = get_conditions(facility)
	total_child_visits = frappe.db.sql("""
		SELECT COUNT(DISTINCT patient)
		FROM `tabPatient Encounter`
		WHERE encounter_date BETWEEN %s AND %s
		AND inpatient_record IS NULL
		AND CAST(patient_age AS UNSIGNED) < 18
		{conditions}
	""".format(conditions=conditions), (from_date, to_date))[0][0]
	
	data.append({
		"indicator": "Total Child Visits",
		"value": total_child_visits,
		"percentage": 100
	})
	
	return data

def get_conditions(facility):
	conditions = []
	if facility:
		conditions.append("medical_department = %s")
	return " AND " + " AND ".join(conditions) if conditions else ""
