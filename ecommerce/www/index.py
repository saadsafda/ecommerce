from frappe.utils import cint

from ecommerce.website import (
	build_theme_css_variables,
	get_brand_showcase,
	get_catalog_items,
	get_featured_item_groups,
	get_home_settings,
	get_homepage_banners,
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
	seo = get_seo_settings()
	home = get_home_settings()

	limit = max(cint(home.get("products_per_section") or 8), 1)
	new_items_payload = get_catalog_items(limit=limit)
	back_items_payload = get_catalog_items(start=limit, limit=limit)
	back_in_store_items = back_items_payload.get("items") or new_items_payload.get("items")

	context.theme_settings = theme
	context.home_settings = home
	context.theme_css_variables = build_theme_css_variables(theme)
	context.banners = get_homepage_banners(limit=6)
	context.featured_categories = get_featured_item_groups(limit=8)
	context.new_items = new_items_payload.get("items", [])
	context.back_in_store_items = back_in_store_items
	context.brands = get_brand_showcase(limit=18)

	title = home.get("home_meta_title") or seo.get("default_meta_title") or home.get("site_title")
	description = home.get("home_meta_description") or seo.get("default_meta_description")
	keywords = home.get("home_meta_keywords") or seo.get("default_meta_keywords")
	image = seo.get("global_og_image")

	context.title = title or home.get("site_title")
	context.metatags = make_meta_tags(
		title=title,
		description=description,
		image=image,
		keywords=keywords,
	)
