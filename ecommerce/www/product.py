import frappe
from frappe.utils import cstr

from ecommerce.website import (
	build_theme_css_variables,
	ensure_product_or_404,
	get_home_settings,
	get_related_items,
	get_theme_settings,
	make_meta_tags,
)


def get_context(context):
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.show_sidebar = False
	context.full_width = True

	item_key = cstr(frappe.form_dict.get("item_key")).strip().strip("/")
	product = ensure_product_or_404(item_key)

	theme = get_theme_settings()
	home = get_home_settings()

	context.theme_settings = theme
	context.home_settings = home
	context.theme_css_variables = build_theme_css_variables(theme)
	context.product = product
	context.related_items = get_related_items(
		item_group=product.get("item_group"),
		exclude_item_key=product.get("route_key"),
		limit=8,
	)

	context.title = cstr(product.get("item_name"))
	context.metatags = make_meta_tags(
		title=cstr(product.get("item_name")),
		description=cstr(product.get("description")),
		image=cstr(product.get("image")),
	)
