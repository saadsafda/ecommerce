import frappe
from frappe.utils import cstr

from ecommerce.customer import is_customer_authenticated
from ecommerce.website import (
	build_theme_css_variables,
	get_home_settings,
	get_seo_settings,
	get_theme_settings,
	make_meta_tags,
)


def get_context(context):
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.show_sidebar = False
	context.full_width = True

	if is_customer_authenticated():
		frappe.local.flags.redirect_location = "/account"
		raise frappe.Redirect

	theme = get_theme_settings()
	home = get_home_settings()
	seo = get_seo_settings()

	context.theme_settings = theme
	context.home_settings = home
	context.theme_css_variables = build_theme_css_variables(theme)
	context.non_customer_user = frappe.session.user != "Guest"
	context.reset_token = cstr(frappe.form_dict.get("token") or "").strip()
	context.redirect_to = frappe.form_dict.get("redirect_to") or "/account"

	title = f"Reset Password | {home.get('site_title')}"
	description = seo.get("default_meta_description") or "Set a new password for customer account."
	context.title = title
	context.metatags = make_meta_tags(title=title, description=description)

