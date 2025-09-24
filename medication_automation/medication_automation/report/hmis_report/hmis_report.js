// Copyright (c) 2025, Byoosi and contributors
// For license information, please see license.txt

frappe.query_reports["HMIS Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_start(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "facility",
			"label": __("Facility"),
			"fieldtype": "Link",
			"options": "Medical Department"
		}
	]
};
