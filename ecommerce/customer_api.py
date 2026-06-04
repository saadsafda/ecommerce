from __future__ import annotations

import frappe
from frappe.utils import cint, cstr

from ecommerce.cart import (
	add_to_cart,
	clear_cart,
	get_cart,
	get_cart_count,
	remove_from_cart,
	update_cart_item,
)
from ecommerce.customer import (
	add_customer_address,
	change_customer_password,
	create_customer_user,
	delete_customer_address,
	get_authenticated_customer_name,
	get_customer_account_data,
	get_customer_addresses,
	get_customer_order_details,
	get_customer_orders,
	get_customer_profile_data,
	is_customer_authenticated,
	login_customer_user,
	logout_customer_user,
	place_order,
	reset_customer_password,
	send_customer_password_reset,
	update_customer_address,
	update_customer_profile_data,
)


# ─────────────────────────────────────────────────────────
# Auth & Account
# ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["GET"])
def customer_session():
	customer_name = get_authenticated_customer_name()
	if not customer_name:
		return {"authenticated": False, "is_customer_user": False}

	return {
		"authenticated": True,
		"is_customer_user": is_customer_authenticated(),
		"account": get_customer_account_data(order_limit=10, customer_name=customer_name),
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_signup(first_name=None, last_name=None, email=None, password=None, mobile_no=None):
	return create_customer_user(
		email=cstr(email or ""),
		password=cstr(password or ""),
		first_name=cstr(first_name or ""),
		last_name=cstr(last_name or ""),
		mobile_no=cstr(mobile_no or ""),
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_login(email=None, password=None):
	return login_customer_user(cstr(email or ""), cstr(password or ""))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_logout():
	return logout_customer_user()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def customer_account():
	return get_customer_account_data(order_limit=20)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def customer_profile():
	return get_customer_profile_data()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_update_profile(
	first_name=None,
	last_name=None,
	mobile_no=None,
	customer_name=None,
	website=None,
	language=None,
):
	return update_customer_profile_data(
		first_name=cstr(first_name or ""),
		last_name=cstr(last_name or ""),
		mobile_no=cstr(mobile_no or ""),
		customer_name=cstr(customer_name or ""),
		website=cstr(website or ""),
		language=cstr(language or ""),
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_change_password(old_password=None, new_password=None):
	return change_customer_password(
		old_password=cstr(old_password or ""),
		new_password=cstr(new_password or ""),
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_request_password_reset(email=None):
	return send_customer_password_reset(cstr(email or ""))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_reset_password(token=None, new_password=None):
	return reset_customer_password(
		token=cstr(token or ""),
		new_password=cstr(new_password or ""),
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def customer_orders(start=0, page_length=20):
	return get_customer_orders(start=cint(start), limit=max(cint(page_length), 1))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def customer_order_details(order_name: str):
	return get_customer_order_details(order_name=cstr(order_name or ""))


# ─────────────────────────────────────────────────────────
# Cart
# ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["GET"])
def cart_get():
	"""Return current cart contents and totals."""
	return get_cart()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def cart_add(item_code=None, qty=1):
	"""Add item to cart."""
	return add_to_cart(item_code=cstr(item_code or ""), qty=max(cint(qty), 1))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def cart_update(item_code=None, qty=0):
	"""Update item quantity in cart."""
	return update_cart_item(item_code=cstr(item_code or ""), qty=cint(qty))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def cart_remove(item_code=None):
	"""Remove item from cart."""
	return remove_from_cart(item_code=cstr(item_code or ""))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def cart_clear():
	"""Clear entire cart."""
	return clear_cart()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def cart_count():
	"""Return cart item count for badge display."""
	return {"count": get_cart_count()}


# ─────────────────────────────────────────────────────────
# Checkout
# ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["POST"])
def checkout_place_order(billing_address=None, shipping_address=None, notes=None):
	"""Place an order from the current cart. Requires authentication."""
	return place_order(
		billing_address_name=cstr(billing_address or ""),
		shipping_address_name=cstr(shipping_address or ""),
		notes=cstr(notes or ""),
	)


# ─────────────────────────────────────────────────────────
# Address Management
# ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["GET"])
def customer_addresses():
	"""Get all addresses for the authenticated customer."""
	return get_customer_addresses()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_add_address(
	address_title=None,
	address_type=None,
	address_line1=None,
	address_line2=None,
	city=None,
	state=None,
	country=None,
	pincode=None,
	phone=None,
	email_id=None,
	is_primary_address=0,
	is_shipping_address=0,
):
	"""Add a new address for the authenticated customer."""
	return add_customer_address(
		address_title=cstr(address_title or ""),
		address_type=cstr(address_type or "Billing"),
		address_line1=cstr(address_line1 or ""),
		address_line2=cstr(address_line2 or ""),
		city=cstr(city or ""),
		state=cstr(state or ""),
		country=cstr(country or ""),
		pincode=cstr(pincode or ""),
		phone=cstr(phone or ""),
		email_id=cstr(email_id or ""),
		is_primary_address=cint(is_primary_address),
		is_shipping_address=cint(is_shipping_address),
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_update_address_api(
	address_name=None,
	address_title=None,
	address_type=None,
	address_line1=None,
	address_line2=None,
	city=None,
	state=None,
	country=None,
	pincode=None,
	phone=None,
	email_id=None,
	is_primary_address=0,
	is_shipping_address=0,
):
	"""Update an existing address."""
	return update_customer_address(
		address_name=cstr(address_name or ""),
		address_title=cstr(address_title or ""),
		address_type=cstr(address_type or ""),
		address_line1=cstr(address_line1 or ""),
		address_line2=cstr(address_line2 or ""),
		city=cstr(city or ""),
		state=cstr(state or ""),
		country=cstr(country or ""),
		pincode=cstr(pincode or ""),
		phone=cstr(phone or ""),
		email_id=cstr(email_id or ""),
		is_primary_address=cint(is_primary_address),
		is_shipping_address=cint(is_shipping_address),
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def customer_delete_address_api(address_name=None):
	"""Delete an address."""
	return delete_customer_address(address_name=cstr(address_name or ""))
