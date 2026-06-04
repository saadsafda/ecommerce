from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "website_login_email",
			"label": "Website Login Email",
			"fieldtype": "Data",
			"module": "Ecommerce",
			"insert_after": "email_id",
			"in_standard_filter": 1,
			"description": "Email address used by customer website authentication.",
		},
		{
			"fieldname": "website_login_password",
			"label": "Website Login Password",
			"fieldtype": "Password",
			"module": "Ecommerce",
			"insert_after": "website_login_email",
			"hidden": 1,
			"read_only": 1,
			"description": "Managed by Ecommerce customer APIs.",
		},
	]
}


def execute():
	if not frappe.db.exists("DocType", "Customer"):
		return

	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)

	if frappe.db.has_column("Customer", "website_login_email") and frappe.db.has_column("Customer", "email_id"):
		frappe.db.sql(
			"""
			update `tabCustomer`
			set website_login_email = email_id
			where ifnull(website_login_email, '') = ''
			  and ifnull(email_id, '') != ''
			"""
		)
