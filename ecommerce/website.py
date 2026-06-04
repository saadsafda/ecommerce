from __future__ import annotations

from typing import Any
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

THEME_SETTINGS_DOCTYPE = "Website Theme Settings"
SEO_SETTINGS_DOCTYPE = "Website SEO Settings"
HOME_SETTINGS_DOCTYPE = "Website Home Settings"
HOMEPAGE_BANNER_DOCTYPE = "Website Homepage Banner"

THEME_FIELDS = [
	"logo",
	"mobile_logo",
	"favicon",
	"primary_color",
	"secondary_color",
	"background_color",
	"text_color",
	"header_background_color",
	"footer_background_color",
	"heading_font_family",
	"body_font_family",
]

SEO_FIELDS = [
	"default_meta_title",
	"default_meta_description",
	"default_meta_keywords",
	"global_og_image",
	"google_analytics_id",
	"facebook_pixel_id",
	"custom_header_scripts",
]

HOME_FIELDS = [
	"site_title",
	"top_bar_text",
	"hotline_number",
	"primary_cta_label",
	"primary_cta_route",
	"secondary_cta_label",
	"secondary_cta_route",
	"hero_title",
	"hero_subtitle",
	"featured_categories_title",
	"new_items_title",
	"back_in_store_title",
	"brands_section_title",
	"products_per_section",
	"show_featured_categories",
	"show_new_items",
	"show_back_in_store",
	"show_brands",
	"home_meta_title",
	"home_meta_description",
	"home_meta_keywords",
]

DEFAULT_THEME_SETTINGS = frappe._dict(
	{
		"logo": "",
		"mobile_logo": "",
		"favicon": "",
		"primary_color": "#1a3a6b",
		"secondary_color": "#e8b84b",
		"background_color": "#f7f9ff",
		"text_color": "#181c20",
		"header_background_color": "#1a3a6b",
		"footer_background_color": "#112646",
		"heading_font_family": "Poppins",
		"body_font_family": "Poppins",
	}
)

DEFAULT_HOME_SETTINGS = frappe._dict(
	{
		"site_title": "Frappe Ecommerce",
		"top_bar_text": "FREE FREIGHT ON ORDERS OVER $1,500 | OFFICIAL B2B DISTRIBUTOR",
		"hotline_number": "",
		"primary_cta_label": "Shop Now",
		"primary_cta_route": "/shop",
		"secondary_cta_label": "Contact Sales",
		"secondary_cta_route": "/contact",
		"hero_title": "Industrial Grade Solutions for Modern Business",
		"hero_subtitle": "Professional tools and equipment for your business needs. Browse our wholesale catalog.",
		"featured_categories_title": "Featured Categories",
		"new_items_title": "New In Store",
		"back_in_store_title": "Back In Store",
		"brands_section_title": "Trusted By Industry Leaders",
		"products_per_section": 8,
		"show_featured_categories": 1,
		"show_new_items": 1,
		"show_back_in_store": 1,
		"show_brands": 1,
		"home_meta_title": "",
		"home_meta_description": "",
		"home_meta_keywords": "",
	}
)


def update_website_context(context):
	from ecommerce.customer import get_authenticated_customer_name

	theme = get_theme_settings()
	seo = get_seo_settings()
	home = get_home_settings()

	context.ecommerce_theme = theme
	context.ecommerce_seo = seo
	context.ecommerce_home_settings = home
	context.ecommerce_theme_css_variables = build_theme_css_variables(theme)

	if theme.get("favicon"):
		context.favicon = theme.favicon

	custom_header_scripts = cstr(seo.get("custom_header_scripts"))
	if custom_header_scripts:
		context.head_html = f"{cstr(context.get('head_html'))}\n{custom_header_scripts}".strip()

	context.customer_authenticated = bool(get_authenticated_customer_name())

	return {}


def get_theme_settings() -> frappe._dict:
	settings = frappe._dict(DEFAULT_THEME_SETTINGS.copy())
	settings.update(_get_single_values(THEME_SETTINGS_DOCTYPE, THEME_FIELDS))
	return settings


def get_seo_settings() -> frappe._dict:
	return frappe._dict(_get_single_values(SEO_SETTINGS_DOCTYPE, SEO_FIELDS))


def get_home_settings() -> frappe._dict:
	settings = frappe._dict(DEFAULT_HOME_SETTINGS.copy())
	settings.update(_get_single_values(HOME_SETTINGS_DOCTYPE, HOME_FIELDS))
	settings.products_per_section = cint(settings.get("products_per_section") or 8)
	return settings


def get_homepage_banners(limit: int = 5) -> list[dict[str, Any]]:
	if not doctype_exists(HOMEPAGE_BANNER_DOCTYPE):
		return []

	return frappe.get_all(
		HOMEPAGE_BANNER_DOCTYPE,
		filters={"is_active": 1},
		fields=[
			"name",
			"banner_title",
			"subtitle",
			"desktop_image",
			"mobile_image",
			"button_text",
			"button_route",
			"badge_text",
			"sort_order",
		],
		order_by="sort_order asc, modified desc",
		limit_page_length=limit,
	)


def get_catalog_items(
	search: str = "",
	item_group: str = "",
	brand: str = "",
	start: int = 0,
	limit: int = 24,
) -> dict[str, Any]:
	start = max(cint(start), 0)
	limit = max(cint(limit), 1)
	search = cstr(search).strip()
	item_group = cstr(item_group).strip()
	brand = cstr(brand).strip()

	if doctype_exists("Website Item"):
		return _get_website_items(
			search=search,
			item_group=item_group,
			brand=brand,
			start=start,
			limit=limit,
		)

	if doctype_exists("Item"):
		return _get_item_records(
			search=search,
			item_group=item_group,
			brand=brand,
			start=start,
			limit=limit,
		)

	return {"items": [], "total_count": 0, "start": start, "limit": limit}


def get_catalog_item(item_key: str) -> dict[str, Any] | None:
	item_key = cstr(item_key).strip().strip("/")
	if not item_key:
		return None

	if doctype_exists("Website Item"):
		candidates = frappe.get_all(
			"Website Item",
			filters={"published": 1},
			or_filters={"route": item_key, "name": item_key, "item_code": item_key},
			fields=[
				"name",
				"item_code",
				"web_item_name",
				"short_description",
				"web_long_description",
				"description",
				"website_image",
				"brand",
				"item_group",
				"route",
			],
			limit_page_length=1,
		)
		if candidates:
			item = _normalize_website_item(candidates[0])
			item.update(_get_price_for_items([item.get("item_code")]).get(item.get("item_code"), {}))
			return item

	if doctype_exists("Item"):
		row = frappe.db.get_value(
			"Item",
			item_key,
			["name", "item_name", "description", "image", "brand", "item_group", "disabled"],
			as_dict=True,
		)
		if row and not cint(row.get("disabled")):
			item = _normalize_item(row)
			item.update(_get_price_for_items([item.get("item_code")]).get(item.get("item_code"), {}))
			return item

	return None


def get_related_items(item_group: str = "", exclude_item_key: str = "", limit: int = 8) -> list[dict[str, Any]]:
	payload = get_catalog_items(item_group=item_group, limit=max(cint(limit) + 1, 2))
	items = payload.get("items", [])
	if not exclude_item_key:
		return items[:limit]

	exclude_item_key = cstr(exclude_item_key).strip("/")
	return [
		item
		for item in items
		if cstr(item.get("route_key")).strip("/") != exclude_item_key and cstr(item.get("item_code")) != exclude_item_key
	][:limit]


def get_featured_item_groups(limit: int = 8) -> list[dict[str, Any]]:
	if not doctype_exists("Item Group"):
		return []

	return frappe.get_all(
		"Item Group",
		filters={"parent_item_group": "All Item Groups"},
		fields=["name", "item_group_name", "image"],
		order_by="modified desc",
		limit_page_length=max(cint(limit), 1),
	)


def get_brand_showcase(limit: int = 16) -> list[dict[str, Any]]:
	if not doctype_exists("Brand"):
		return []

	return frappe.get_all(
		"Brand",
		fields=["name", "brand", "image", "description"],
		order_by="modified desc",
		limit_page_length=max(cint(limit), 1),
	)


def get_brand_filters(limit: int = 50) -> list[dict[str, Any]]:
	if not doctype_exists("Brand"):
		return []

	return frappe.get_all(
		"Brand",
		fields=["name", "brand"],
		order_by="brand asc",
		limit_page_length=max(cint(limit), 1),
	)


def get_item_group_filters(limit: int = 50) -> list[dict[str, Any]]:
	if not doctype_exists("Item Group"):
		return []

	return frappe.get_all(
		"Item Group",
		filters={"parent_item_group": "All Item Groups"},
		fields=["name", "item_group_name"],
		order_by="item_group_name asc",
		limit_page_length=max(cint(limit), 1),
	)


def make_meta_tags(
	title: str = "",
	description: str = "",
	image: str = "",
	keywords: str = "",
) -> dict[str, Any]:
	seo = get_seo_settings()
	tags = frappe._dict()

	tags.title = cstr(title or seo.get("default_meta_title") or "")
	tags.description = cstr(description or seo.get("default_meta_description") or "")
	tags.image = cstr(image or seo.get("global_og_image") or "")
	tags["keywords"] = cstr(keywords or seo.get("default_meta_keywords") or "")
	return tags


def build_theme_css_variables(theme: dict[str, Any] | None = None) -> str:
	theme = frappe._dict(theme or get_theme_settings())
	return (
		f"--ec-primary:{theme.primary_color};"
		f"--ec-secondary:{theme.secondary_color};"
		f"--ec-accent-1:{theme.primary_color};"
		f"--ec-accent-2:{theme.secondary_color};"
		f"--ec-bg:{theme.background_color};"
		f"--ec-text:{theme.text_color};"
		f"--ec-heading:{theme.text_color};"
		f"--ec-header-bg:{theme.header_background_color};"
		f"--ec-footer-bg:{theme.footer_background_color};"
		f"--ec-surface:{theme.header_background_color};"
		f"--ec-heading-font:'{theme.heading_font_family}',sans-serif;"
		f"--ec-body-font:'{theme.body_font_family}',sans-serif;"
		f"--ec-font-heading:'{theme.heading_font_family}',sans-serif;"
		f"--ec-font-body:'{theme.body_font_family}',sans-serif;"
	)


def doctype_exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _get_single_values(doctype: str, fields: list[str]) -> dict:
	if not doctype_exists(doctype):
		return {}
	return frappe.get_cached_value(doctype, doctype, fields, as_dict=True) or {}


def _get_website_items(search: str, item_group: str, brand: str, start: int, limit: int) -> dict[str, Any]:
	filters: dict[str, Any] = {"published": 1}
	if item_group:
		filters["item_group"] = item_group
	if brand:
		filters["brand"] = brand

	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"web_item_name": ["like", like], "item_code": ["like", like]}

	fields = [
		"name",
		"item_code",
		"web_item_name",
		"short_description",
		"description",
		"website_image",
		"brand",
		"item_group",
		"route",
	]
	rows = frappe.get_all(
		"Website Item",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="modified desc",
		start=start,
		limit_page_length=limit,
	)

	count_row = frappe.get_all(
		"Website Item",
		filters=filters,
		or_filters=or_filters,
		fields=["count(name) as total_count"],
		limit_page_length=1,
	)
	total_count = cint((count_row[0] if count_row else {}).get("total_count"))

	items = [_normalize_website_item(row) for row in rows]
	attach_prices(items)

	return {"items": items, "total_count": total_count, "start": start, "limit": limit}


def _get_item_records(search: str, item_group: str, brand: str, start: int, limit: int) -> dict[str, Any]:
	filters: dict[str, Any] = {"disabled": 0}
	if item_group:
		filters["item_group"] = item_group
	if brand:
		filters["brand"] = brand

	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"item_name": ["like", like], "name": ["like", like]}

	fields = ["name", "item_name", "description", "image", "brand", "item_group"]
	rows = frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="modified desc",
		start=start,
		limit_page_length=limit,
	)

	count_row = frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=["count(name) as total_count"],
		limit_page_length=1,
	)
	total_count = cint((count_row[0] if count_row else {}).get("total_count"))

	items = [_normalize_item(row) for row in rows]
	attach_prices(items)

	return {"items": items, "total_count": total_count, "start": start, "limit": limit}


def _normalize_website_item(row: dict[str, Any]) -> dict[str, Any]:
	item_code = cstr(row.get("item_code"))
	route = cstr(row.get("route")).strip("/")
	route_key = route or item_code
	return {
		"name": row.get("name"),
		"item_code": item_code,
		"item_name": cstr(row.get("web_item_name") or row.get("name")),
		"description": cstr(row.get("short_description") or row.get("description") or ""),
		"image": row.get("website_image"),
		"brand": row.get("brand"),
		"item_group": row.get("item_group"),
		"route_key": route_key,
		"product_route": f"/product/{quote(route_key, safe='/')}",
	}


def _normalize_item(row: dict[str, Any]) -> dict[str, Any]:
	item_code = cstr(row.get("name"))
	item_slug = frappe.scrub(cstr(row.get("item_name") or item_code))
	route_key = item_code or item_slug
	return {
		"name": row.get("name"),
		"item_code": item_code,
		"item_name": cstr(row.get("item_name") or item_code),
		"description": cstr(row.get("description") or ""),
		"image": row.get("image"),
		"brand": row.get("brand"),
		"item_group": row.get("item_group"),
		"route_key": route_key,
		"product_route": f"/product/{quote(route_key, safe='/')}",
	}


def attach_prices(items: list[dict[str, Any]]) -> None:
	item_codes = [item.get("item_code") for item in items if item.get("item_code")]
	price_map = _get_price_for_items(item_codes)

	for item in items:
		item.update(price_map.get(item.get("item_code"), {}))


def _get_price_for_items(item_codes: list[str]) -> dict[str, dict[str, Any]]:
	item_codes = [code for code in item_codes if code]
	if not item_codes or not doctype_exists("Item Price"):
		return {}

	rows = frappe.get_all(
		"Item Price",
		filters={"item_code": ["in", item_codes], "selling": 1},
		fields=["item_code", "price_list_rate", "currency", "price_list", "modified"],
		order_by="modified desc",
		limit_page_length=0,
	)

	result: dict[str, dict[str, Any]] = {}
	for row in rows:
		item_code = row.get("item_code")
		if not item_code or item_code in result:
			continue

		amount = flt(row.get("price_list_rate"))
		currency = cstr(row.get("currency") or frappe.defaults.get_global_default("currency") or "")
		result[item_code] = {
			"price": amount,
			"currency": currency,
			"formatted_price": frappe.utils.fmt_money(amount, currency=currency) if amount else "",
			"price_list": row.get("price_list"),
		}

	return result


def ensure_product_or_404(item_key: str) -> dict[str, Any]:
	product = get_catalog_item(item_key)
	if product:
		return product

	frappe.throw(_("Product not found"), frappe.DoesNotExistError)
	return {}
