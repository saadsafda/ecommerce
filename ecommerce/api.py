import frappe
from frappe.utils import cint

from ecommerce.website import (
	ensure_product_or_404,
	get_brand_showcase,
	get_catalog_item,
	get_catalog_items,
	get_featured_item_groups,
	get_home_settings,
	get_homepage_banners,
	get_seo_settings,
	get_theme_settings,
)


@frappe.whitelist(allow_guest=True)
def get_website_settings():
	"""Return theme and SEO settings for website pages."""
	return {
		"theme": get_theme_settings(),
		"seo": get_seo_settings(),
	}


@frappe.whitelist(allow_guest=True)
def get_homepage_data():
	"""Return homepage payload for website apps."""
	home = get_home_settings()
	limit = max(cint(home.get("products_per_section") or 8), 1)

	new_items_payload = get_catalog_items(limit=limit)
	back_items_payload = get_catalog_items(start=limit, limit=limit)
	back_items = back_items_payload.get("items") or new_items_payload.get("items")

	return {
		"theme": get_theme_settings(),
		"seo": get_seo_settings(),
		"home": home,
		"banners": get_homepage_banners(),
		"featured_categories": get_featured_item_groups(),
		"new_items": new_items_payload.get("items", []),
		"back_in_store_items": back_items,
		"brands": get_brand_showcase(),
	}


@frappe.whitelist(allow_guest=True)
def get_shop_items(search=None, item_group=None, brand=None, start=0, page_length=24):
	"""Return paginated catalog items for listing pages."""
	return get_catalog_items(
		search=search or "",
		item_group=item_group or "",
		brand=brand or "",
		start=cint(start),
		limit=max(cint(page_length), 1),
	)


@frappe.whitelist(allow_guest=True)
def get_product_data(item_key: str):
	"""Return details for one catalog item."""
	return ensure_product_or_404(item_key)


@frappe.whitelist(allow_guest=True)
def get_product_if_exists(item_key: str):
	"""Return product dict or null when item does not exist."""
	return get_catalog_item(item_key)
