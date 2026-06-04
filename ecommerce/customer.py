from __future__ import annotations

from typing import Any
from urllib.parse import quote

import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import get_contact_name
from frappe.utils import add_days, cint, cstr, flt, get_url, getdate, nowdate, random_string
from frappe.utils.nestedset import get_root_of
from frappe.utils.password import check_password, update_password

CUSTOMER_LOGIN_EMAIL_FIELD = "website_login_email"
CUSTOMER_PASSWORD_FIELD = "website_login_password"

CUSTOMER_SESSION_COOKIE = "ecommerce_customer_sid"
CUSTOMER_SESSION_CACHE_KEY = "ecommerce_customer_session"
CUSTOMER_RESET_CACHE_KEY = "ecommerce_customer_reset"

CUSTOMER_SESSION_TTL = 60 * 60 * 24 * 30
CUSTOMER_RESET_TTL = 60 * 30


def doctype_exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _normalize_email(email: str | None) -> str:
	return cstr(email).strip().lower()


def _customer_meta_has_field(fieldname: str) -> bool:
	if not doctype_exists("Customer"):
		return False
	return frappe.get_meta("Customer").has_field(fieldname)


def _get_customer_by_email(email: str | None) -> str | None:
	email = _normalize_email(email)
	if not email or not doctype_exists("Customer"):
		return None

	search_fields: list[str] = []
	if _customer_meta_has_field(CUSTOMER_LOGIN_EMAIL_FIELD):
		search_fields.append(CUSTOMER_LOGIN_EMAIL_FIELD)
	if _customer_meta_has_field("email_id"):
		search_fields.append("email_id")

	for fieldname in search_fields:
		row = frappe.db.sql(
			f"""
			select name
			from `tabCustomer`
			where lower(ifnull(`{fieldname}`, '')) = %s
			limit 1
			""",
			(email,),
			as_dict=True,
		)
		if row:
			return cstr(row[0].name)

	return None


def _get_customer_email(customer_name: str) -> str:
	if not customer_name:
		return ""

	fields: list[str] = []
	if _customer_meta_has_field(CUSTOMER_LOGIN_EMAIL_FIELD):
		fields.append(CUSTOMER_LOGIN_EMAIL_FIELD)
	if _customer_meta_has_field("email_id"):
		fields.append("email_id")
	if not fields:
		return ""

	values = frappe.db.get_value("Customer", customer_name, fields, as_dict=True) or {}
	login_email = _normalize_email(values.get(CUSTOMER_LOGIN_EMAIL_FIELD))
	if login_email:
		return login_email

	return _normalize_email(values.get("email_id"))


def _session_cache_key(token: str) -> str:
	return f"{CUSTOMER_SESSION_CACHE_KEY}:{token}"


def _reset_cache_key(token: str) -> str:
	return f"{CUSTOMER_RESET_CACHE_KEY}:{token}"


def _get_request_cookie(cookie_name: str) -> str:
	request = getattr(frappe.local, "request", None)
	if not request:
		return ""
	return cstr(request.cookies.get(cookie_name) or "").strip()


def _set_customer_session(customer_name: str) -> str:
	token = random_string(48)
	cache_payload = {"customer": customer_name}

	frappe.cache().set_value(
		_session_cache_key(token),
		cache_payload,
		expires_in_sec=CUSTOMER_SESSION_TTL,
	)

	cookie_manager = getattr(frappe.local, "cookie_manager", None)
	if cookie_manager:
		cookie_manager.set_cookie(
			CUSTOMER_SESSION_COOKIE,
			token,
			httponly=True,
			samesite="Lax",
			max_age=CUSTOMER_SESSION_TTL,
		)

	frappe.local.flags.ecommerce_customer_name = customer_name
	return token


def _clear_customer_session() -> None:
	token = _get_request_cookie(CUSTOMER_SESSION_COOKIE)
	if token:
		frappe.cache().delete_value(_session_cache_key(token))

	cookie_manager = getattr(frappe.local, "cookie_manager", None)
	if cookie_manager:
		cookie_manager.delete_cookie(CUSTOMER_SESSION_COOKIE)

	frappe.local.flags.ecommerce_customer_name = None


def get_authenticated_customer_name() -> str | None:
	cached_name = cstr(getattr(frappe.local.flags, "ecommerce_customer_name", "")).strip()
	if cached_name and frappe.db.exists("Customer", cached_name):
		return cached_name

	token = _get_request_cookie(CUSTOMER_SESSION_COOKIE)
	if not token:
		return None

	session_data = frappe.cache().get_value(_session_cache_key(token), expires=True)
	customer_name = ""
	if isinstance(session_data, dict):
		customer_name = cstr(session_data.get("customer")).strip()
	else:
		customer_name = cstr(session_data).strip()

	if customer_name and frappe.db.exists("Customer", customer_name):
		frappe.local.flags.ecommerce_customer_name = customer_name
		return customer_name

	frappe.cache().delete_value(_session_cache_key(token))
	return None


def is_customer_authenticated() -> bool:
	return bool(get_authenticated_customer_name())


def is_customer_user(user: str | None = None) -> bool:
	"""Compatibility helper used by page controllers."""
	user = cstr(user).strip()
	if user and user != "Guest" and user != cstr(getattr(frappe.session, "user", "")):
		return bool(frappe.db.exists("Customer", user) or _get_customer_by_email(user))

	return is_customer_authenticated()


def require_customer_user(user: str | None = None) -> str:
	provided = cstr(user).strip()
	if provided and provided != "Guest":
		if frappe.db.exists("Customer", provided):
			return provided

		customer_from_email = _get_customer_by_email(provided)
		if customer_from_email:
			return customer_from_email

	customer_name = get_authenticated_customer_name()
	if not customer_name:
		frappe.throw(_("Please login to continue"), frappe.PermissionError)

	return customer_name


def get_customer_for_user(user: str) -> str | None:
	user = cstr(user).strip()
	if not user or user == "Guest":
		return None

	if frappe.db.exists("Customer", user):
		return user

	return _get_customer_by_email(user)


def ensure_customer_for_user(
	user: str,
	customer_name: str | None = None,
	mobile_no: str | None = None,
) -> str:
	email = _normalize_email(user)
	if not email:
		frappe.throw(_("Email is required"), frappe.ValidationError)

	existing = _get_customer_by_email(email)
	if existing:
		_ensure_customer_contact_link(
			existing,
			email,
			customer_name_for_contact=customer_name,
			mobile_no=mobile_no,
		)
		return existing

	first_name, last_name = _split_name(cstr(customer_name))
	return _create_customer_record(
		email=email,
		first_name=first_name,
		last_name=last_name,
		mobile_no=cstr(mobile_no),
		customer_name=cstr(customer_name),
	)


def _split_name(full_name: str) -> tuple[str, str]:
	parts = [cstr(part).strip() for part in cstr(full_name).split(" ") if cstr(part).strip()]
	if not parts:
		return "", ""
	if len(parts) == 1:
		return parts[0], ""
	return parts[0], " ".join(parts[1:])


def _join_name(first_name: str, last_name: str, fallback: str = "") -> str:
	joined = " ".join([part for part in [cstr(first_name).strip(), cstr(last_name).strip()] if part]).strip()
	if joined:
		return joined
	return cstr(fallback).strip()


def _validate_password(password: str) -> None:
	if not password:
		frappe.throw(_("Password is required"), frappe.ValidationError)
	if len(password) < 8:
		frappe.throw(_("Password must be at least 8 characters"), frappe.ValidationError)


def _get_profile_name_parts(customer_label: str) -> tuple[str, str]:
	first_name, last_name = _split_name(customer_label)
	return first_name, last_name


def get_customer_profile_data(user: str | None = None) -> dict[str, Any]:
	customer_name = require_customer_user(user)

	customer_data = frappe.db.get_value(
		"Customer",
		customer_name,
		[
			"name",
			"customer_name",
			"customer_group",
			"territory",
			"website",
			"language",
			"default_currency",
			"default_price_list",
			"tax_id",
			"creation",
			"mobile_no",
			"image",
		],
		as_dict=True,
	) or {}

	email = _get_customer_email(customer_name)
	mobile_no = cstr(customer_data.get("mobile_no") or "")
	full_name = cstr(customer_data.get("customer_name") or "")
	first_name, last_name = _get_profile_name_parts(full_name)

	return {
		"user": {
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"full_name": full_name,
			"mobile_no": mobile_no,
			"user_image": customer_data.get("image"),
			"last_login": None,
		},
		"customer": {
			"name": customer_data.get("name"),
			"customer_name": full_name,
			"customer_group": customer_data.get("customer_group"),
			"territory": customer_data.get("territory"),
			"website": cstr(customer_data.get("website") or ""),
			"language": customer_data.get("language"),
			"default_currency": customer_data.get("default_currency"),
			"default_price_list": customer_data.get("default_price_list"),
			"tax_id": cstr(customer_data.get("tax_id") or ""),
			"creation": customer_data.get("creation"),
			"primary_email": email,
			"primary_phone": mobile_no,
		},
	}


def update_customer_profile_data(
	first_name: str = "",
	last_name: str = "",
	mobile_no: str = "",
	customer_name: str = "",
	website: str = "",
	language: str = "",
) -> dict[str, Any]:
	customer_id = require_customer_user()
	customer_doc = frappe.get_doc("Customer", customer_id)

	first_name = cstr(first_name).strip()
	last_name = cstr(last_name).strip()
	mobile_no = cstr(mobile_no).strip()
	customer_name = cstr(customer_name).strip()
	website = cstr(website).strip()
	language = cstr(language).strip()

	resolved_name = customer_name or _join_name(first_name, last_name, fallback=customer_doc.customer_name)
	updated = False

	if resolved_name and customer_doc.customer_name != resolved_name:
		customer_doc.customer_name = resolved_name
		updated = True
	if _customer_meta_has_field("mobile_no") and cstr(customer_doc.mobile_no or "") != mobile_no:
		customer_doc.mobile_no = mobile_no
		updated = True
	if cstr(customer_doc.website or "") != website:
		customer_doc.website = website
		updated = True
	if cstr(customer_doc.language or "") != language:
		customer_doc.language = language
		updated = True

	if updated:
		customer_doc.flags.ignore_permissions = True
		customer_doc.flags.ignore_mandatory = True
		customer_doc.save(ignore_permissions=True)

	email = _get_customer_email(customer_doc.name)
	if email:
		_ensure_customer_contact_link(
			customer_doc.name,
			email,
			customer_name_for_contact=customer_doc.customer_name,
			mobile_no=mobile_no,
		)

	return get_customer_profile_data(customer_doc.name)


def get_customer_orders(
	user: str | None = None,
	start: int = 0,
	limit: int = 20,
) -> dict[str, Any]:
	customer_name = require_customer_user(user)
	start = max(cint(start), 0)
	limit = max(cint(limit), 1)

	if not doctype_exists("Sales Order"):
		return {"orders": [], "total_count": 0, "start": start, "limit": limit}

	order_filters = {"customer": customer_name, "docstatus": 1}
	orders = frappe.get_all(
		"Sales Order",
		filters=order_filters,
		fields=[
			"name",
			"transaction_date",
			"delivery_date",
			"status",
			"delivery_status",
			"grand_total",
			"rounded_total",
			"currency",
			"per_delivered",
			"per_billed",
		],
		order_by="transaction_date desc, modified desc",
		start=start,
		limit_page_length=limit,
		ignore_permissions=True,
	)

	count_data = frappe.get_all(
		"Sales Order",
		filters=order_filters,
		fields=["count(name) as total_count"],
		limit_page_length=1,
		ignore_permissions=True,
	)
	total_count = cint((count_data[0] if count_data else {}).get("total_count") or 0)

	for row in orders:
		total_amount = flt(row.get("rounded_total") or row.get("grand_total"))
		currency = cstr(row.get("currency") or "")
		row["total_amount"] = total_amount
		row["formatted_total"] = frappe.utils.fmt_money(total_amount, currency=currency) if currency else total_amount

	return {
		"orders": orders,
		"total_count": total_count,
		"start": start,
		"limit": limit,
	}


def get_customer_order_details(order_name: str, user: str | None = None) -> dict[str, Any]:
	customer_name = require_customer_user(user)
	order_name = cstr(order_name).strip()
	if not order_name:
		frappe.throw(_("Order ID is required"), frappe.ValidationError)

	if not doctype_exists("Sales Order"):
		frappe.throw(_("Sales Order DocType not found"), frappe.DoesNotExistError)

	order = frappe.db.get_value(
		"Sales Order",
		{"name": order_name, "customer": customer_name, "docstatus": 1},
		[
			"name",
			"customer",
			"customer_name",
			"transaction_date",
			"delivery_date",
			"status",
			"delivery_status",
			"grand_total",
			"rounded_total",
			"currency",
			"shipping_address",
			"contact_email",
			"contact_mobile",
			"per_delivered",
			"per_billed",
		],
		as_dict=True,
	)
	if not order:
		frappe.throw(_("Order not found"), frappe.DoesNotExistError)

	items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": order_name, "parenttype": "Sales Order"},
		fields=["item_code", "item_name", "description", "qty", "uom", "rate", "amount"],
		order_by="idx asc",
		ignore_permissions=True,
	)

	currency = cstr(order.get("currency") or "")
	for row in items:
		row["formatted_rate"] = frappe.utils.fmt_money(flt(row.get("rate")), currency=currency) if currency else row.get("rate")
		row["formatted_amount"] = (
			frappe.utils.fmt_money(flt(row.get("amount")), currency=currency) if currency else row.get("amount")
		)

	total_amount = flt(order.get("rounded_total") or order.get("grand_total"))
	order["total_amount"] = total_amount
	order["formatted_total"] = frappe.utils.fmt_money(total_amount, currency=currency) if currency else total_amount

	return {"order": order, "items": items}


def _get_customer_account_metrics(customer_name: str, currency: str = "") -> dict[str, Any]:
	metrics = {
		"recent_orders_count": 0,
		"ytd_spend": 0,
		"formatted_ytd_spend": frappe.utils.fmt_money(0, currency=currency) if currency else "0",
		"active_quotes_count": 0,
	}

	if doctype_exists("Sales Order"):
		recent_from = add_days(nowdate(), -30)
		metrics["recent_orders_count"] = frappe.db.count(
			"Sales Order",
			{
				"customer": customer_name,
				"transaction_date": [">=", recent_from],
				"docstatus": 1,
			},
		)

		year_start = getdate(nowdate()).replace(month=1, day=1)
		spend = frappe.db.sql(
			"""
			select sum(coalesce(nullif(rounded_total, 0), grand_total, 0)) as total_spend
			from `tabSales Order`
			where customer = %s
				and transaction_date >= %s
				and docstatus = 1
			""",
			(customer_name, year_start),
			as_dict=True,
		)
		ytd_spend = flt((spend[0] if spend else {}).get("total_spend"))
		metrics["ytd_spend"] = ytd_spend
		metrics["formatted_ytd_spend"] = frappe.utils.fmt_money(ytd_spend, currency=currency) if currency else ytd_spend

	if doctype_exists("Quotation"):
		metrics["active_quotes_count"] = frappe.db.count(
			"Quotation",
			{
				"quotation_to": "Customer",
				"party_name": customer_name,
				"status": ["not in", ["Ordered", "Lost", "Cancelled", "Expired"]],
				"docstatus": ["<", 2],
			},
		)

	return metrics


def get_customer_account_data(order_limit: int = 20, customer_name: str | None = None) -> dict[str, Any]:
	customer_name = require_customer_user(customer_name)
	profile = get_customer_profile_data(customer_name)
	orders = get_customer_orders(user=customer_name, limit=order_limit)
	addresses = get_customer_addresses(customer_name)
	currency = cstr(profile.get("customer", {}).get("default_currency") or "")
	if not currency and orders.get("orders"):
		currency = cstr(orders.get("orders", [{}])[0].get("currency") or "")

	return {
		"authenticated": True,
		"user": profile.get("user", {}),
		"customer": profile.get("customer", {}),
		"orders": orders.get("orders", []),
		"orders_total_count": orders.get("total_count", 0),
		"addresses": addresses,
		"primary_address": addresses[0] if addresses else {},
		"metrics": _get_customer_account_metrics(customer_name, currency=currency),
	}


def create_customer_user(
	email: str,
	password: str,
	first_name: str = "",
	last_name: str = "",
	mobile_no: str = "",
) -> dict[str, Any]:
	email = _normalize_email(email)
	password = cstr(password)
	first_name = cstr(first_name).strip()
	last_name = cstr(last_name).strip()
	mobile_no = cstr(mobile_no).strip()

	if not email:
		frappe.throw(_("Email is required"), frappe.ValidationError)
	_validate_password(password)

	if _get_customer_by_email(email):
		frappe.throw(_("An account already exists with this email"), frappe.DuplicateEntryError)

	customer_name = _create_customer_record(
		email=email,
		first_name=first_name,
		last_name=last_name,
		mobile_no=mobile_no,
	)

	update_password(
		customer_name,
		password,
		doctype="Customer",
		fieldname=CUSTOMER_PASSWORD_FIELD,
	)

	_set_customer_session(customer_name)
	try:
		from ecommerce.cart import merge_guest_cart_into_customer_order

		merge_guest_cart_into_customer_order(customer_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Customer Cart Merge Failed")
	return get_customer_account_data(order_limit=10, customer_name=customer_name)


def login_customer_user(email: str, password: str) -> dict[str, Any]:
	email = _normalize_email(email)
	password = cstr(password)
	if not email or not password:
		frappe.throw(_("Email and password are required"), frappe.ValidationError)

	customer_name = _get_customer_by_email(email)
	if not customer_name:
		frappe.throw(_("Incorrect email or password"), frappe.AuthenticationError)

	try:
		check_password(customer_name, password, doctype="Customer", fieldname=CUSTOMER_PASSWORD_FIELD)
	except frappe.AuthenticationError:
		frappe.throw(_("Incorrect email or password"), frappe.AuthenticationError)

	_set_customer_session(customer_name)
	try:
		from ecommerce.cart import merge_guest_cart_into_customer_order

		merge_guest_cart_into_customer_order(customer_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Customer Cart Merge Failed")
	return get_customer_account_data(order_limit=10, customer_name=customer_name)


def logout_customer_user() -> dict[str, Any]:
	_clear_customer_session()
	return {"authenticated": False}


def change_customer_password(old_password: str, new_password: str) -> dict[str, Any]:
	customer_name = require_customer_user()
	old_password = cstr(old_password)
	new_password = cstr(new_password)
	if not old_password:
		frappe.throw(_("Current password is required"), frappe.ValidationError)
	_validate_password(new_password)

	try:
		check_password(customer_name, old_password, doctype="Customer", fieldname=CUSTOMER_PASSWORD_FIELD)
	except frappe.AuthenticationError:
		frappe.throw(_("Current password is incorrect"), frappe.AuthenticationError)

	update_password(
		customer_name,
		new_password,
		doctype="Customer",
		fieldname=CUSTOMER_PASSWORD_FIELD,
	)
	return {"updated": True}


def send_customer_password_reset(email: str) -> dict[str, Any]:
	email = _normalize_email(email)
	if not email:
		frappe.throw(_("Email is required"), frappe.ValidationError)

	customer_name = _get_customer_by_email(email)
	if not customer_name:
		return {"sent": True}

	token = random_string(48)
	frappe.cache().set_value(
		_reset_cache_key(token),
		{"customer": customer_name},
		expires_in_sec=CUSTOMER_RESET_TTL,
	)

	reset_url = f"{get_url()}/customer-reset-password?token={quote(token, safe='')}"
	message = (
		"<p>You requested a password reset for your customer account.</p>"
		f"<p><a href=\"{reset_url}\">Click here to reset your password</a></p>"
		"<p>This link will expire in 30 minutes.</p>"
	)

	frappe.sendmail(
		recipients=[email],
		subject="Customer Account Password Reset",
		message=message,
	)

	return {"sent": True}


def reset_customer_password(token: str, new_password: str) -> dict[str, Any]:
	token = cstr(token).strip()
	new_password = cstr(new_password)
	if not token:
		frappe.throw(_("Reset token is required"), frappe.ValidationError)
	_validate_password(new_password)

	reset_data = frappe.cache().get_value(_reset_cache_key(token), expires=True)
	customer_name = ""
	if isinstance(reset_data, dict):
		customer_name = cstr(reset_data.get("customer")).strip()
	else:
		customer_name = cstr(reset_data).strip()

	if not customer_name or not frappe.db.exists("Customer", customer_name):
		frappe.throw(_("Reset link is invalid or expired"), frappe.ValidationError)

	update_password(
		customer_name,
		new_password,
		doctype="Customer",
		fieldname=CUSTOMER_PASSWORD_FIELD,
	)
	frappe.cache().delete_value(_reset_cache_key(token))

	_set_customer_session(customer_name)
	return get_customer_account_data(order_limit=10, customer_name=customer_name)


def _get_default_customer_group() -> str | None:
	default_group = None
	if doctype_exists("Selling Settings"):
		default_group = frappe.db.get_single_value("Selling Settings", "customer_group")
	if default_group:
		return default_group
	return frappe.db.get_value("Customer Group", {}, "name")


def _get_default_territory() -> str | None:
	default_territory = None
	if doctype_exists("Selling Settings"):
		default_territory = frappe.db.get_single_value("Selling Settings", "territory")
	if default_territory:
		return default_territory

	if doctype_exists("Territory"):
		root = get_root_of("Territory")
		if root:
			return root
		return frappe.db.get_value("Territory", {}, "name")

	return None


def _create_customer_record(
	email: str,
	first_name: str = "",
	last_name: str = "",
	mobile_no: str = "",
	customer_name: str = "",
) -> str:
	if not doctype_exists("Customer"):
		frappe.throw(_("Customer DocType is required. Please install ERPNext."), frappe.DoesNotExistError)

	customer_group = _get_default_customer_group()
	territory = _get_default_territory()
	default_name = customer_name or _join_name(first_name, last_name, fallback=email.split("@")[0])

	customer = frappe.new_doc("Customer")
	customer.update(
		{
			"customer_name": default_name,
			"customer_type": "Individual",
			"customer_group": customer_group,
			"territory": territory,
		}
	)

	if _customer_meta_has_field("email_id"):
		customer.email_id = email
	if _customer_meta_has_field(CUSTOMER_LOGIN_EMAIL_FIELD):
		customer.set(CUSTOMER_LOGIN_EMAIL_FIELD, email)
	if _customer_meta_has_field("mobile_no"):
		customer.mobile_no = mobile_no

	customer.flags.ignore_permissions = True
	customer.flags.ignore_mandatory = True
	customer.insert(ignore_permissions=True)

	_ensure_customer_contact_link(
		customer.name,
		email,
		customer_name_for_contact=default_name,
		mobile_no=mobile_no,
	)

	return customer.name


def _ensure_customer_contact_link(
	customer_name: str,
	email: str,
	customer_name_for_contact: str | None = None,
	mobile_no: str | None = None,
) -> None:
	if not doctype_exists("Contact"):
		return

	email = _normalize_email(email)
	if not email:
		return

	name_for_contact = cstr(customer_name_for_contact).strip() or email.split("@")[0]
	mobile_no = cstr(mobile_no).strip()
	contact_name = get_contact_name(email)
	if contact_name:
		contact_doc = frappe.get_doc("Contact", contact_name)
	else:
		contact_doc = frappe.new_doc("Contact")
		contact_doc.first_name = name_for_contact
		contact_doc.append("email_ids", {"email_id": email, "is_primary": 1})

	if not any(_normalize_email(row.email_id) == email for row in contact_doc.email_ids):
		contact_doc.append("email_ids", {"email_id": email})
	for row in contact_doc.email_ids:
		row.is_primary = 1 if _normalize_email(row.email_id) == email else 0

	if mobile_no:
		phone_row = None
		for row in contact_doc.phone_nos:
			if cstr(row.phone) == mobile_no:
				phone_row = row
				break
		if not phone_row:
			phone_row = contact_doc.append("phone_nos", {"phone": mobile_no})
		for row in contact_doc.phone_nos:
			row.is_primary_mobile_no = 1 if row is phone_row else 0

	if not any(link.link_doctype == "Customer" and link.link_name == customer_name for link in contact_doc.links):
		contact_doc.append("links", {"link_doctype": "Customer", "link_name": customer_name})

	contact_doc.flags.ignore_permissions = True
	contact_doc.flags.ignore_mandatory = True
	if contact_doc.is_new():
		contact_doc.insert(ignore_permissions=True)
	else:
		contact_doc.save(ignore_permissions=True)


# ─────────────────────────────────────────────────────────
# Address Management
# ─────────────────────────────────────────────────────────

ADDRESS_FIELDS = [
	"name",
	"address_title",
	"address_type",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"country",
	"pincode",
	"phone",
	"email_id",
	"is_primary_address",
	"is_shipping_address",
]


def get_customer_addresses(customer_name: str | None = None) -> list[dict[str, Any]]:
	"""Get all addresses linked to a customer."""
	customer_name = require_customer_user(customer_name)

	if not doctype_exists("Address"):
		return []

	# Get address names linked to this customer via Dynamic Link
	linked = frappe.get_all(
		"Dynamic Link",
		filters={
			"link_doctype": "Customer",
			"link_name": customer_name,
			"parenttype": "Address",
		},
		fields=["parent"],
		limit_page_length=0,
	)

	if not linked:
		return []

	address_names = list({row.parent for row in linked})

	addresses = frappe.get_all(
		"Address",
		filters={"name": ["in", address_names]},
		fields=ADDRESS_FIELDS,
		order_by="is_primary_address desc, modified desc",
		limit_page_length=0,
	)

	return addresses


def add_customer_address(
	address_title: str = "",
	address_type: str = "Billing",
	address_line1: str = "",
	address_line2: str = "",
	city: str = "",
	state: str = "",
	country: str = "",
	pincode: str = "",
	phone: str = "",
	email_id: str = "",
	is_primary_address: int = 0,
	is_shipping_address: int = 0,
) -> dict[str, Any]:
	"""Create a new address linked to the authenticated customer."""
	customer_name = require_customer_user()

	if not doctype_exists("Address"):
		frappe.throw(_("Address DocType not found"), frappe.DoesNotExistError)

	address_line1 = cstr(address_line1).strip()
	if not address_line1:
		frappe.throw(_("Address Line 1 is required"), frappe.ValidationError)

	city = cstr(city).strip()
	if not city:
		frappe.throw(_("City is required"), frappe.ValidationError)

	address_type = cstr(address_type).strip()
	if address_type not in ("Billing", "Shipping", "Office", "Personal", "Plant", "Postal", "Shop", "Subsidiary", "Warehouse", "Other"):
		address_type = "Billing"

	# Default country
	country = cstr(country).strip()
	if not country:
		country = frappe.db.get_single_value("System Settings", "country") or "Pakistan"

	address_title = cstr(address_title).strip() or cstr(
		frappe.db.get_value("Customer", customer_name, "customer_name") or customer_name
	)

	address = frappe.new_doc("Address")
	address.update(
		{
			"address_title": address_title,
			"address_type": address_type,
			"address_line1": address_line1,
			"address_line2": cstr(address_line2).strip(),
			"city": city,
			"state": cstr(state).strip(),
			"country": country,
			"pincode": cstr(pincode).strip(),
			"phone": cstr(phone).strip(),
			"email_id": cstr(email_id).strip() or _get_customer_email(customer_name),
			"is_primary_address": cint(is_primary_address),
			"is_shipping_address": cint(is_shipping_address),
		}
	)
	address.append("links", {"link_doctype": "Customer", "link_name": customer_name})

	address.flags.ignore_permissions = True
	address.flags.ignore_mandatory = True
	address.insert(ignore_permissions=True)

	return {
		"address": frappe.db.get_value("Address", address.name, ADDRESS_FIELDS, as_dict=True),
	}


def update_customer_address(
	address_name: str,
	address_title: str = "",
	address_type: str = "",
	address_line1: str = "",
	address_line2: str = "",
	city: str = "",
	state: str = "",
	country: str = "",
	pincode: str = "",
	phone: str = "",
	email_id: str = "",
	is_primary_address: int = 0,
	is_shipping_address: int = 0,
) -> dict[str, Any]:
	"""Update an existing address belonging to the authenticated customer."""
	customer_name = require_customer_user()
	address_name = cstr(address_name).strip()

	if not address_name or not doctype_exists("Address"):
		frappe.throw(_("Address not found"), frappe.DoesNotExistError)

	# Verify ownership
	if not _address_belongs_to_customer(address_name, customer_name):
		frappe.throw(_("Address not found"), frappe.DoesNotExistError)

	address = frappe.get_doc("Address", address_name)

	if cstr(address_title).strip():
		address.address_title = cstr(address_title).strip()
	if cstr(address_type).strip():
		address.address_type = cstr(address_type).strip()
	if cstr(address_line1).strip():
		address.address_line1 = cstr(address_line1).strip()

	address.address_line2 = cstr(address_line2).strip()
	if cstr(city).strip():
		address.city = cstr(city).strip()
	address.state = cstr(state).strip()
	if cstr(country).strip():
		address.country = cstr(country).strip()
	address.pincode = cstr(pincode).strip()
	address.phone = cstr(phone).strip()
	if cstr(email_id).strip():
		address.email_id = cstr(email_id).strip()
	address.is_primary_address = cint(is_primary_address)
	address.is_shipping_address = cint(is_shipping_address)

	address.flags.ignore_permissions = True
	address.flags.ignore_mandatory = True
	address.save(ignore_permissions=True)

	return {
		"address": frappe.db.get_value("Address", address.name, ADDRESS_FIELDS, as_dict=True),
	}


def delete_customer_address(address_name: str) -> dict[str, Any]:
	"""Delete an address belonging to the authenticated customer."""
	customer_name = require_customer_user()
	address_name = cstr(address_name).strip()

	if not address_name or not doctype_exists("Address"):
		frappe.throw(_("Address not found"), frappe.DoesNotExistError)

	if not _address_belongs_to_customer(address_name, customer_name):
		frappe.throw(_("Address not found"), frappe.DoesNotExistError)

	frappe.delete_doc("Address", address_name, ignore_permissions=True, force=True)
	return {"deleted": True}


def _address_belongs_to_customer(address_name: str, customer_name: str) -> bool:
	"""Check if an address is linked to the given customer."""
	return bool(
		frappe.db.exists(
			"Dynamic Link",
			{
				"link_doctype": "Customer",
				"link_name": customer_name,
				"parenttype": "Address",
				"parent": address_name,
			},
		)
	)


# ─────────────────────────────────────────────────────────
# Place Order (Checkout)
# ─────────────────────────────────────────────────────────

def place_order(
	billing_address_name: str = "",
	shipping_address_name: str = "",
	notes: str = "",
) -> dict[str, Any]:
	"""Create a Sales Order from the current cart."""
	from ecommerce.cart import clear_cart, get_cart, get_customer_cart_order

	customer_name = require_customer_user()

	if not doctype_exists("Sales Order"):
		frappe.throw(_("Sales Order DocType not found. Please install ERPNext."), frappe.DoesNotExistError)

	# Get cart
	cart = get_cart()
	cart_items = cart.get("items", [])
	if not cart_items:
		frappe.throw(_("Your cart is empty"), frappe.ValidationError)

	# Validate addresses
	billing_address_name = cstr(billing_address_name).strip()
	shipping_address_name = cstr(shipping_address_name).strip()

	if billing_address_name and not _address_belongs_to_customer(billing_address_name, customer_name):
		frappe.throw(_("Invalid billing address"), frappe.ValidationError)

	if shipping_address_name and not _address_belongs_to_customer(shipping_address_name, customer_name):
		frappe.throw(_("Invalid shipping address"), frappe.ValidationError)

	cart_order_name = cstr(cart.get("sales_order") or "").strip()
	if cart_order_name:
		so = get_customer_cart_order(customer_name)
		if not so or so.name != cart_order_name or so.docstatus != 0:
			frappe.throw(_("Cart order was not found. Please refresh and try again."), frappe.ValidationError)

		if billing_address_name:
			so.customer_address = billing_address_name
		if shipping_address_name:
			so.shipping_address_name = shipping_address_name
		if cstr(notes).strip():
			so.notes = cstr(notes).strip()

		so.transaction_date = frappe.utils.today()
		so.delivery_date = frappe.utils.add_days(frappe.utils.today(), 7)
		for item in so.items:
			item.delivery_date = so.delivery_date

		so.flags.ignore_permissions = True
		so.flags.ignore_mandatory = True
		so.save(ignore_permissions=True)
		so.submit()

		clear_cart()
		total_amount = flt(so.rounded_total or so.grand_total)
		return {
			"order_name": so.name,
			"total_amount": total_amount,
			"formatted_total": frappe.utils.fmt_money(total_amount, currency=so.currency) if so.currency else str(total_amount),
			"status": so.status,
		}

	# Build Sales Order
	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		frappe.throw(_("No company found. Please configure your ERPNext instance."), frappe.ValidationError)

	delivery_date = frappe.utils.add_days(frappe.utils.today(), 7)
	currency = cart.get("currency") or frappe.db.get_single_value("Global Defaults", "default_currency") or "PKR"

	so = frappe.new_doc("Sales Order")
	so.update(
		{
			"customer": customer_name,
			"company": company,
			"transaction_date": frappe.utils.today(),
			"delivery_date": delivery_date,
			"currency": currency,
			"order_type": "Shopping Cart",
		}
	)

	if billing_address_name:
		so.customer_address = billing_address_name
	if shipping_address_name:
		so.shipping_address_name = shipping_address_name

	if cstr(notes).strip():
		so.notes = cstr(notes).strip()

	for item in cart_items:
		so.append(
			"items",
			{
				"item_code": item.get("item_code"),
				"item_name": item.get("item_name"),
				"qty": cint(item.get("qty", 1)),
				"rate": flt(item.get("price", 0)),
				"uom": item.get("uom", "Nos"),
				"delivery_date": delivery_date,
			},
		)

	so.flags.ignore_permissions = True
	so.flags.ignore_mandatory = True
	so.insert(ignore_permissions=True)
	so.submit()

	# Clear cart after successful order
	clear_cart()

	total_amount = flt(so.rounded_total or so.grand_total)
	return {
		"order_name": so.name,
		"total_amount": total_amount,
		"formatted_total": frappe.utils.fmt_money(total_amount, currency=so.currency) if so.currency else str(total_amount),
		"status": so.status,
	}
