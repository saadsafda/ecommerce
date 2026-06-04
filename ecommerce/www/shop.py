from urllib.parse import urlencode

import frappe
from frappe.utils import cint, cstr

from ecommerce.website import (
	build_theme_css_variables,
	get_brand_filters,
	get_catalog_items,
	get_home_settings,
	get_item_group_filters,
	get_seo_settings,
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
	seo = get_seo_settings()
	theme_css_variables = build_theme_css_variables(theme)

	search = cstr(frappe.form_dict.get("q")).strip()
	item_group = cstr(frappe.form_dict.get("item_group")).strip()
	brand = cstr(frappe.form_dict.get("brand")).strip()
	start = max(cint(frappe.form_dict.get("start") or 0), 0)
	page_length = 24

	catalog_payload = get_catalog_items(
		search=search,
		item_group=item_group,
		brand=brand,
		start=start,
		limit=page_length,
	)
	items = catalog_payload.get("items", [])
	total_count = cint(catalog_payload.get("total_count"))

	context.theme_settings = theme
	context.home_settings = home
	context.theme_css_variables = theme_css_variables
	context.items = items
	context.total_count = total_count
	context.start = start
	context.page_length = page_length
	context.has_previous = start > 0
	context.has_next = (start + page_length) < total_count
	context.previous_query = _build_query(search, item_group, brand, max(start - page_length, 0))
	context.next_query = _build_query(search, item_group, brand, start + page_length)
	context.search_query = search
	context.selected_item_group = item_group
	context.selected_brand = brand
	context.item_group_filters = get_item_group_filters()
	context.brand_filters = get_brand_filters()

	title = f"Shop | {home.get('site_title')}"
	description = seo.get("default_meta_description") or "Browse our wholesale catalog."
	context.title = title
	context.metatags = make_meta_tags(title=title, description=description)


def _build_query(search: str, item_group: str, brand: str, start: int) -> str:
	params = {}
	if search:
		params["q"] = search
	if item_group:
		params["item_group"] = item_group
	if brand:
		params["brand"] = brand
	if start > 0:
		params["start"] = start

	return urlencode(params)
