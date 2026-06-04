import frappe
from frappe.utils import now_datetime

from ecommerce.customer import get_customer_account_data, is_customer_authenticated
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

	if not is_customer_authenticated():
		frappe.local.flags.redirect_location = "/customer-login?redirect_to=/account"
		raise frappe.Redirect

	theme = get_theme_settings()
	home = get_home_settings()
	seo = get_seo_settings()

	context.theme_settings = theme
	context.home_settings = home
	context.theme_css_variables = build_theme_css_variables(theme)
	context.non_customer_user = False
	context.account_error = ""
	context.account = {"user": {}, "customer": {}, "orders": [], "orders_total_count": 0}
	context.current_year = now_datetime().year

	try:
		context.account = get_customer_account_data(order_limit=20)
	except Exception:
		context.account_error = "Unable to load customer account at the moment."

	title = f"Customer Account | {home.get('site_title')}"
	description = seo.get("default_meta_description") or "Customer account, profile and order history."
	context.title = title
	context.metatags = make_meta_tags(title=title, description=description)
