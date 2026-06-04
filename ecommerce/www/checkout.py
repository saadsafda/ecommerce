import frappe
from frappe.utils import now_datetime

from ecommerce.cart import get_cart
from ecommerce.customer import (
	get_customer_addresses,
	get_customer_profile_data,
	is_customer_authenticated,
)
from ecommerce.website import (
	build_theme_css_variables,
	get_home_settings,
	get_theme_settings,
	make_meta_tags,
)


def get_context(context):
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.show_sidebar = False
	context.full_width = True

	if not is_customer_authenticated():
		frappe.local.flags.redirect_location = "/customer-login?redirect_to=/checkout"
		raise frappe.Redirect

	theme = get_theme_settings()
	home = get_home_settings()

	context.theme_settings = theme
	context.home_settings = home
	context.theme_css_variables = build_theme_css_variables(theme)

	cart = get_cart()
	context.cart = cart
	context.cart_items = cart.get("items", [])
	context.cart_count = cart.get("item_count", 0)
	context.cart_subtotal = cart.get("formatted_subtotal", "0")
	context.cart_shipping = cart.get("formatted_shipping_estimate", "0.00")
	context.cart_tax = cart.get("formatted_tax_amount", "0.00")
	context.cart_total = cart.get("formatted_grand_total", context.cart_subtotal)
	context.current_year = now_datetime().year

	# If cart is empty, redirect to cart page
	if not cart.get("items"):
		frappe.local.flags.redirect_location = "/cart"
		raise frappe.Redirect

	# Load customer addresses
	try:
		context.addresses = get_customer_addresses()
	except Exception:
		context.addresses = []

	context.billing_addresses = [a for a in context.addresses if a.get("address_type") == "Billing" or a.get("is_primary_address")]
	context.shipping_addresses = [a for a in context.addresses if a.get("address_type") == "Shipping" or a.get("is_shipping_address")]

	# If no specific billing/shipping, show all
	if not context.billing_addresses:
		context.billing_addresses = context.addresses
	if not context.shipping_addresses:
		context.shipping_addresses = context.addresses

	context.default_billing_address = context.billing_addresses[0] if context.billing_addresses else {}
	context.default_shipping_address = context.shipping_addresses[0] if context.shipping_addresses else context.default_billing_address

	try:
		context.customer_profile = get_customer_profile_data()
	except Exception:
		context.customer_profile = {"user": {}, "customer": {}}
	context.checkout_user = context.customer_profile.get("user", {})
	context.checkout_customer = context.customer_profile.get("customer", {})

	title = f"Checkout | {home.get('site_title', 'Store')}"
	context.title = title
	context.metatags = make_meta_tags(title=title, description="Complete your order")
