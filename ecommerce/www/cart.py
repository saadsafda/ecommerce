import frappe
from frappe.utils import now_datetime

from ecommerce.cart import get_cart
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

	title = f"Shopping Cart | {home.get('site_title', 'Store')}"
	context.title = title
	context.metatags = make_meta_tags(title=title, description="Your shopping cart")
