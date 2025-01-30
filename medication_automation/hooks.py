# -*- coding: utf-8 -*-
from . import __version__ as app_version

app_name = "medication_automation"
app_title = "Medication Automation"
app_publisher = "Byoosi"
app_description = "Medication Automation"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "info@byoosi.com"
app_license = "MIT"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "medication_automation",
# 		"logo": "/assets/medication_automation/logo.png",
# 		"title": "Medication Automation",
# 		"route": "/medication_automation",
# 		"has_permission": "medication_automation.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/medication_automation/css/medication_automation.css"
app_include_js = "/assets/medication_automation/js/patient_encounter.js"

# include js, css files in header of web template
# web_include_css = "/assets/medication_automation/css/medication_automation.css"
# web_include_js = "/assets/medication_automation/js/medication_automation.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "medication_automation/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Patient Encounter": "public/js/patient_encounter.js"
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "medication_automation/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "medication_automation.utils.jinja_methods",
# 	"filters": "medication_automation.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "medication_automation.install.before_install"
# after_install = "medication_automation.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "medication_automation.uninstall.before_uninstall"
# after_uninstall = "medication_automation.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "medication_automation.utils.before_app_install"
# after_app_install = "medication_automation.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "medication_automation.utils.before_app_uninstall"
# after_app_uninstall = "medication_automation.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "medication_automation.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Inpatient Medication Entry": {
		"on_submit": "medication_automation.doc_events.on_submit_medication_entry"
	}
}

# Scheduled Tasks
# ---------------
scheduler_events = {
	"cron": {
		"* * * * *": [
			"medication_automation.medication_automation.scheduler.schedule_medication_entries"
		]
	}
}

# Testing
# -------

# before_tests = "medication_automation.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "medication_automation.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "medication_automation.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["medication_automation.utils.before_request"]
# after_request = ["medication_automation.utils.after_request"]

# Job Events
# ----------
# before_job = ["medication_automation.utils.before_job"]
# after_job = ["medication_automation.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"medication_automation.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Custom Scripts

