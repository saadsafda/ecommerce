from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, random_string, today

from ecommerce.website import _get_price_for_items, doctype_exists

CART_COOKIE = "ecommerce_cart_id"
CART_CACHE_PREFIX = "ecommerce_cart"
CART_TTL = 60 * 60 * 24 * 30  # 30 days
CART_ORDER_TYPE = "Shopping Cart"


def _get_cart_token() -> str:
	"""Get or create a cart token from cookie."""
	cached_token = cstr(getattr(frappe.local.flags, "ecommerce_cart_token", "")).strip()
	if cached_token:
		return cached_token

	request = getattr(frappe.local, "request", None)
	token = ""
	if request:
		token = cstr(request.cookies.get(CART_COOKIE) or "").strip()

	if not token:
		token = random_string(48)
		cookie_manager = getattr(frappe.local, "cookie_manager", None)
		if cookie_manager:
			cookie_manager.set_cookie(
				CART_COOKIE,
				token,
				httponly=True,
				samesite="Lax",
				max_age=CART_TTL,
			)

	frappe.local.flags.ecommerce_cart_token = token
	return token


def _get_existing_cart_token() -> str:
	request = getattr(frappe.local, "request", None)
	if not request:
		return ""
	return cstr(request.cookies.get(CART_COOKIE) or "").strip()


def _cart_cache_key(token: str) -> str:
	return f"{CART_CACHE_PREFIX}:{token}"


def _load_cart_data(token: str) -> dict[str, Any]:
	"""Load raw cart dict from Redis."""
	raw = frappe.cache().get_value(_cart_cache_key(token), expires=True)
	if isinstance(raw, dict):
		return raw
	if isinstance(raw, str):
		try:
			return json.loads(raw)
		except (json.JSONDecodeError, ValueError):
			pass
	return {"items": {}}


def _save_cart_data(token: str, data: dict[str, Any]) -> None:
	"""Persist cart dict to Redis."""
	frappe.cache().set_value(
		_cart_cache_key(token),
		data,
		expires_in_sec=CART_TTL,
	)


def _get_authenticated_customer_name() -> str:
	try:
		from ecommerce.customer import get_authenticated_customer_name

		return cstr(get_authenticated_customer_name() or "").strip()
	except Exception:
		return ""


def _get_default_company() -> str:
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company and doctype_exists("Company"):
		company = frappe.db.get_value("Company", {}, "name")
	return cstr(company or "").strip()


def _get_default_currency() -> str:
	currency = frappe.db.get_single_value("Global Defaults", "default_currency")
	return cstr(currency or "PKR").strip()


def _get_default_price_list() -> str:
	if doctype_exists("Selling Settings"):
		return cstr(frappe.db.get_single_value("Selling Settings", "selling_price_list") or "").strip()
	return ""


def _get_delivery_date() -> str:
	return add_days(today(), 7)


def _get_draft_sales_order_name(customer_name: str) -> str:
	if not customer_name or not doctype_exists("Sales Order"):
		return ""

	rows = frappe.get_all(
		"Sales Order",
		filters={
			"customer": customer_name,
			"docstatus": 0,
			"order_type": CART_ORDER_TYPE,
		},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=1,
		ignore_permissions=True,
	)
	return cstr(rows[0].name if rows else "").strip()


def get_customer_cart_order(customer_name: str | None = None):
	"""Return the authenticated customer's draft cart Sales Order, if any."""
	customer_name = cstr(customer_name or _get_authenticated_customer_name()).strip()
	order_name = _get_draft_sales_order_name(customer_name)
	if not order_name:
		return None
	return frappe.get_doc("Sales Order", order_name)


def _new_customer_sales_order(customer_name: str):
	company = _get_default_company()
	if not company:
		frappe.throw(_("No company found. Please configure your ERPNext instance."), frappe.ValidationError)

	so = frappe.new_doc("Sales Order")
	so.update(
		{
			"customer": customer_name,
			"company": company,
			"transaction_date": today(),
			"delivery_date": _get_delivery_date(),
			"currency": _get_default_currency(),
			"order_type": CART_ORDER_TYPE,
		}
	)

	price_list = _get_default_price_list()
	if price_list:
		so.selling_price_list = price_list
	if frappe.get_meta("Sales Order").has_field("ignore_pricing_rule"):
		so.ignore_pricing_rule = 1

	return so


def _get_or_new_customer_sales_order(customer_name: str):
	return get_customer_cart_order(customer_name) or _new_customer_sales_order(customer_name)


def _get_sales_order_item_values(item_code: str, qty: int) -> dict[str, Any]:
	item_name = item_code
	uom = "Nos"
	if doctype_exists("Item"):
		row = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom"], as_dict=True)
		if row:
			item_name = cstr(row.get("item_name") or item_code)
			uom = cstr(row.get("stock_uom") or "Nos")

	price_info = _get_price_for_items([item_code]).get(item_code, {})
	return {
		"item_code": item_code,
		"item_name": item_name,
		"qty": max(cint(qty), 1),
		"rate": flt(price_info.get("price", 0)),
		"uom": uom,
		"delivery_date": _get_delivery_date(),
	}


def _find_sales_order_item(so, item_code: str):
	for row in so.items:
		if cstr(row.item_code) == item_code:
			return row
	return None


def _persist_customer_sales_order(so):
	if not so.items:
		if not so.is_new():
			frappe.delete_doc("Sales Order", so.name, ignore_permissions=True, force=True)
		return None

	so.transaction_date = today()
	so.delivery_date = _get_delivery_date()
	for row in so.items:
		row.delivery_date = _get_delivery_date()

	so.flags.ignore_permissions = True
	so.flags.ignore_mandatory = True
	if so.is_new():
		so.insert(ignore_permissions=True)
	else:
		so.save(ignore_permissions=True)
	return so


def _sales_order_to_cart_data(so) -> dict[str, Any]:
	items: dict[str, dict[str, Any]] = {}
	if not so:
		return {"items": {}}

	for row in so.items:
		item_code = cstr(row.item_code).strip()
		if not item_code:
			continue
		if item_code in items:
			items[item_code]["qty"] = cint(items[item_code].get("qty", 0)) + cint(row.qty)
			continue
		items[item_code] = {
			"qty": max(cint(row.qty), 1),
			"item_name": cstr(row.item_name or item_code),
			"uom": cstr(row.uom or "Nos"),
			"price": flt(row.rate),
		}

	return {"items": items, "sales_order": so.name}


def _add_item_to_customer_sales_order(customer_name: str, item_code: str, qty: int) -> None:
	so = _get_or_new_customer_sales_order(customer_name)
	row = _find_sales_order_item(so, item_code)
	if row:
		row.qty = cint(row.qty) + max(cint(qty), 1)
		price_info = _get_price_for_items([item_code]).get(item_code, {})
		if price_info:
			row.rate = flt(price_info.get("price", row.rate))
	else:
		so.append("items", _get_sales_order_item_values(item_code, qty))
	_persist_customer_sales_order(so)


def _set_customer_sales_order_item_qty(customer_name: str, item_code: str, qty: int) -> None:
	so = get_customer_cart_order(customer_name)
	if not so:
		if qty > 0:
			_add_item_to_customer_sales_order(customer_name, item_code, qty)
		return

	row = _find_sales_order_item(so, item_code)
	if qty <= 0:
		if row:
			so.remove(row)
	elif row:
		row.qty = qty
		price_info = _get_price_for_items([item_code]).get(item_code, {})
		if price_info:
			row.rate = flt(price_info.get("price", row.rate))
	else:
		so.append("items", _get_sales_order_item_values(item_code, qty))

	_persist_customer_sales_order(so)


def _clear_customer_sales_order(customer_name: str) -> None:
	so = get_customer_cart_order(customer_name)
	if so and so.docstatus == 0:
		frappe.delete_doc("Sales Order", so.name, ignore_permissions=True, force=True)


def merge_guest_cart_into_customer_order(customer_name: str | None = None) -> None:
	"""Move the current cookie cart into the customer's draft Sales Order once per request."""
	customer_name = cstr(customer_name or _get_authenticated_customer_name()).strip()
	if not customer_name or getattr(frappe.local.flags, "ecommerce_guest_cart_merged", False):
		return

	frappe.local.flags.ecommerce_guest_cart_merged = True
	token = _get_existing_cart_token()
	if not token:
		return

	data = _load_cart_data(token)
	items = data.get("items", {})
	if not items:
		return

	for item_code, item in items.items():
		_add_item_to_customer_sales_order(customer_name, cstr(item_code), max(cint(item.get("qty", 1)), 1))

	_save_cart_data(token, {"items": {}})
	request = getattr(frappe.local, "request", None)
	if cstr(getattr(request, "method", "")).upper() == "GET":
		frappe.db.commit()


def _enrich_cart_items(items_dict: dict[str, dict]) -> list[dict[str, Any]]:
	"""Enrich cart items with live prices and item details."""
	if not items_dict:
		return []

	item_codes = list(items_dict.keys())
	price_map = _get_price_for_items(item_codes)

	# Fetch item details
	item_details = {}
	if doctype_exists("Item"):
		rows = frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes], "disabled": 0},
			fields=["name", "item_name", "image", "item_group", "brand", "stock_uom"],
			limit_page_length=0,
		)
		for row in rows:
			item_details[row.name] = row

	enriched = []
	for item_code, cart_item in items_dict.items():
		qty = max(cint(cart_item.get("qty", 1)), 1)
		detail = item_details.get(item_code, {})
		price_info = price_map.get(item_code, {})
		price_value = price_info.get("price")
		unit_price = flt(cart_item.get("price", 0) if price_value in (None, "") else price_value)
		currency = cstr(price_info.get("currency", cart_item.get("currency", "")))

		line_total = flt(unit_price * qty)
		formatted_price = price_info.get("formatted_price") or ""
		if not formatted_price and unit_price:
			formatted_price = frappe.utils.fmt_money(unit_price, currency=currency) if currency else f"{unit_price:,.2f}"
		formatted_line_total = (
			frappe.utils.fmt_money(line_total, currency=currency) if currency else f"{line_total:,.2f}"
		)

		enriched.append(
			{
				"item_code": item_code,
				"item_name": cstr(detail.get("item_name") or cart_item.get("item_name") or item_code),
				"image": detail.get("image") or cart_item.get("image") or "",
				"brand": detail.get("brand") or cart_item.get("brand") or "",
				"item_group": detail.get("item_group") or "",
				"uom": detail.get("stock_uom") or "Nos",
				"qty": qty,
				"price": unit_price,
				"currency": currency,
				"formatted_price": formatted_price,
				"line_total": line_total,
				"formatted_line_total": formatted_line_total,
			}
		)

	return enriched


def get_cart() -> dict[str, Any]:
	"""Return the full enriched cart."""
	customer_name = _get_authenticated_customer_name()
	sales_order_name = ""
	if customer_name and doctype_exists("Sales Order"):
		merge_guest_cart_into_customer_order(customer_name)
		so = get_customer_cart_order(customer_name)
		data = _sales_order_to_cart_data(so)
		sales_order_name = cstr(data.get("sales_order") or "")
	else:
		token = _get_cart_token()
		data = _load_cart_data(token)

	items = _enrich_cart_items(data.get("items", {}))

	subtotal = sum(flt(item.get("line_total", 0)) for item in items)
	item_count = sum(cint(item.get("qty", 0)) for item in items)
	currency = items[0].get("currency", "") if items else ""
	shipping_estimate = 45 if subtotal else 0
	tax_rate = 0.05
	tax_amount = flt(subtotal * tax_rate)
	grand_total = flt(subtotal + shipping_estimate + tax_amount)

	def fmt(amount: float) -> str:
		return frappe.utils.fmt_money(amount, currency=currency) if currency else f"{flt(amount):,.2f}"

	return {
		"items": items,
		"item_count": item_count,
		"subtotal": subtotal,
		"formatted_subtotal": fmt(subtotal),
		"shipping_estimate": shipping_estimate,
		"formatted_shipping_estimate": fmt(shipping_estimate),
		"tax_rate": tax_rate,
		"tax_amount": tax_amount,
		"formatted_tax_amount": fmt(tax_amount),
		"grand_total": grand_total,
		"formatted_grand_total": fmt(grand_total),
		"currency": currency,
		"sales_order": sales_order_name,
	}


def add_to_cart(item_code: str, qty: int = 1) -> dict[str, Any]:
	"""Add an item to cart or increment its quantity."""
	item_code = cstr(item_code).strip()
	qty = max(cint(qty), 1)

	if not item_code:
		frappe.throw(_("Item code is required"), frappe.ValidationError)

	# Validate item exists
	if doctype_exists("Item"):
		if not frappe.db.exists("Item", item_code):
			frappe.throw(_("Item not found"), frappe.DoesNotExistError)
		if cint(frappe.db.get_value("Item", item_code, "disabled")):
			frappe.throw(_("Item is not available"), frappe.ValidationError)

	customer_name = _get_authenticated_customer_name()
	if customer_name and doctype_exists("Sales Order"):
		merge_guest_cart_into_customer_order(customer_name)
		_add_item_to_customer_sales_order(customer_name, item_code, qty)
		return get_cart()

	token = _get_cart_token()
	data = _load_cart_data(token)
	items = data.get("items", {})
	if item_code in items:
		items[item_code]["qty"] = cint(items[item_code].get("qty", 0)) + qty
	else:
		# Store minimal info; full details enriched on retrieval
		item_name = ""
		image = ""
		if doctype_exists("Item"):
			row = frappe.db.get_value("Item", item_code, ["item_name", "image"], as_dict=True)
			if row:
				item_name = cstr(row.get("item_name", ""))
				image = cstr(row.get("image", ""))

		items[item_code] = {
			"qty": qty,
			"item_name": item_name,
			"image": image,
		}

	data["items"] = items
	_save_cart_data(token, data)

	return get_cart()


def update_cart_item(item_code: str, qty: int) -> dict[str, Any]:
	"""Set exact quantity for an item. qty=0 removes it."""
	item_code = cstr(item_code).strip()
	qty = max(cint(qty), 0)

	if not item_code:
		frappe.throw(_("Item code is required"), frappe.ValidationError)

	customer_name = _get_authenticated_customer_name()
	if customer_name and doctype_exists("Sales Order"):
		merge_guest_cart_into_customer_order(customer_name)
		_set_customer_sales_order_item_qty(customer_name, item_code, qty)
		return get_cart()

	token = _get_cart_token()
	data = _load_cart_data(token)
	items = data.get("items", {})
	if qty == 0:
		items.pop(item_code, None)
	elif item_code in items:
		items[item_code]["qty"] = qty
	else:
		# Item not in cart, add it
		return add_to_cart(item_code, qty)

	data["items"] = items
	_save_cart_data(token, data)

	return get_cart()


def remove_from_cart(item_code: str) -> dict[str, Any]:
	"""Remove an item from cart entirely."""
	return update_cart_item(item_code, 0)


def clear_cart() -> dict[str, Any]:
	"""Empty the entire cart."""
	customer_name = _get_authenticated_customer_name()
	if customer_name and doctype_exists("Sales Order"):
		_clear_customer_sales_order(customer_name)

	token = _get_cart_token()
	_save_cart_data(token, {"items": {}})
	return get_cart()


def get_cart_count() -> int:
	"""Return total item count for badge display."""
	cart = get_cart()
	return cint(cart.get("item_count", 0))


def get_cart_totals() -> dict[str, Any]:
	"""Return summary info for the cart."""
	cart = get_cart()
	return {
		"item_count": cart.get("item_count", 0),
		"subtotal": cart.get("subtotal", 0),
		"formatted_subtotal": cart.get("formatted_subtotal", "0"),
		"currency": cart.get("currency", ""),
	}
