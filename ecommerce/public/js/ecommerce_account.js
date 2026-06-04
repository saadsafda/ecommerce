(() => {
	const root = document.querySelector(
		"[data-account-page], [data-customer-login-page], [data-customer-register-page], [data-customer-forgot-page], [data-customer-reset-page], [data-checkout-page]"
	);
	if (!root) return;

	const messageBox = root.querySelector("[data-account-message], [data-checkout-message]");
	const messageBaseClass =
		messageBox && messageBox.hasAttribute("data-checkout-message")
			? "ec-checkout-message"
			: "ec-account-message";

	const getCookie = (name) => {
		const parts = (`; ${document.cookie}`).split(`; ${name}=`);
		if (parts.length === 2) return parts.pop().split(";").shift();
		return "";
	};

	const getCsrfToken = () =>
		window.csrf_token ||
		(window.frappe && (frappe.csrf_token || (frappe.boot && frappe.boot.csrf_token))) ||
		getCookie("csrf_token") ||
		"";

	const showMessage = (text, type = "success") => {
		if (!messageBox) return;
		if (!text) {
			messageBox.textContent = "";
			messageBox.className = messageBaseClass;
			return;
		}

		messageBox.textContent = text;
		messageBox.className = `${messageBaseClass} is-${type}`;
	};

	const extractErrorMessage = (payload) => {
		if (!payload) return "Request failed.";
		if (payload.message && typeof payload.message === "string") return payload.message;
		if (payload.exception) return payload.exception;
		if (payload.exc) return "Server error occurred.";
		if (payload._server_messages) {
			try {
				const messages = JSON.parse(payload._server_messages);
				const first = messages && messages.length ? JSON.parse(messages[0]) : null;
				if (first && first.message) return first.message;
			} catch (e) {
				return "Server error occurred.";
			}
		}
		return "Request failed.";
	};

	const callApi = async (method, values = {}, requestMethod = "POST") => {
		let url = `/api/method/${method}`;
		const options = {
			method: requestMethod,
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		};

		if (requestMethod === "GET") {
			const query = new URLSearchParams(values).toString();
			if (query) url = `${url}?${query}`;
		} else {
			const csrfToken = getCsrfToken();
			options.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8";
			if (csrfToken) {
				options.headers["X-Frappe-CSRF-Token"] = csrfToken;
			}
			options.body = new URLSearchParams(values).toString();
		}

		const response = await fetch(url, options);
		let payload = {};
		try {
			payload = await response.json();
		} catch (e) {
			throw new Error("Unexpected server response.");
		}

		if (!response.ok || payload.exc) {
			throw new Error(extractErrorMessage(payload));
		}

		return payload.message;
	};

	const bindAuthForms = () => {
		const redirectInput = root.querySelector("[data-redirect-to]");
		const redirectTo = (redirectInput && redirectInput.value) || "/account";
		const loginForm = root.querySelector("[data-account-login-form]");
		const signupForm = root.querySelector("[data-account-signup-form]");
		const resetForm = root.querySelector("[data-account-reset-form]");
		const resetConfirmForm = root.querySelector("[data-account-reset-confirm-form]");

		if (loginForm) {
			loginForm.addEventListener("submit", async (event) => {
				event.preventDefault();
				showMessage("");
				const formData = new FormData(loginForm);
				const submitButton = loginForm.querySelector("[data-login-submit]");
				const originalButtonHtml = submitButton ? submitButton.innerHTML : "";
				if (submitButton) {
					submitButton.disabled = true;
					submitButton.innerHTML =
						'<span class="ec-login-spinner"></span><span>Authenticating...</span>';
				}
				try {
					await callApi("ecommerce.customer_api.customer_login", Object.fromEntries(formData), "POST");
					window.location.href = redirectTo;
				} catch (error) {
					if (submitButton) {
						submitButton.disabled = false;
						submitButton.innerHTML = originalButtonHtml;
					}
					showMessage(error.message, "error");
				}
			});
		}

		if (signupForm) {
			signupForm.addEventListener("submit", async (event) => {
				event.preventDefault();
				showMessage("");
				const formData = new FormData(signupForm);
				const submitButton = signupForm.querySelector("[data-register-submit]");
				const originalButtonHtml = submitButton ? submitButton.innerHTML : "";
				if (submitButton) {
					submitButton.disabled = true;
					submitButton.innerHTML =
						'<span class="ec-register-spinner"></span><span>Creating Account...</span>';
				}
				try {
					await callApi("ecommerce.customer_api.customer_signup", Object.fromEntries(formData), "POST");
					window.location.href = redirectTo;
				} catch (error) {
					if (submitButton) {
						submitButton.disabled = false;
						submitButton.innerHTML = originalButtonHtml;
					}
					showMessage(error.message, "error");
				}
			});
		}

		if (resetForm) {
			resetForm.addEventListener("submit", async (event) => {
				event.preventDefault();
				showMessage("");
				const formData = new FormData(resetForm);
				try {
					await callApi(
						"ecommerce.customer_api.customer_request_password_reset",
						Object.fromEntries(formData),
						"POST"
					);
					showMessage("Password reset instructions sent if the account exists.", "success");
					resetForm.reset();
				} catch (error) {
					showMessage(error.message, "error");
				}
			});
		}

		if (resetConfirmForm) {
			resetConfirmForm.addEventListener("submit", async (event) => {
				event.preventDefault();
				showMessage("");
				const formData = new FormData(resetConfirmForm);
				const payload = Object.fromEntries(formData);
				if ((payload.new_password || "") !== (payload.confirm_password || "")) {
					showMessage("Password confirmation does not match.", "error");
					return;
				}
				try {
					await callApi(
						"ecommerce.customer_api.customer_reset_password",
						{
							token: payload.token || "",
							new_password: payload.new_password || "",
						},
						"POST"
					);
					window.location.href = redirectTo;
				} catch (error) {
					showMessage(error.message, "error");
				}
			});
		}
	};

	const bindLoginDesignControls = () => {
		const passwordToggle = root.querySelector("[data-password-toggle]");
		if (passwordToggle) {
			passwordToggle.addEventListener("click", () => {
				const passwordInput = root.querySelector("#customer-login-password");
				const icon = root.querySelector("[data-password-icon]");
				if (!passwordInput) return;

				const isHidden = passwordInput.type === "password";
				passwordInput.type = isHidden ? "text" : "password";
				passwordToggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
				if (icon) {
					icon.textContent = isHidden ? "visibility_off" : "visibility";
				}
			});
		}

		const loginBackground = root.querySelector(".ec-login-bg");
		if (loginBackground) {
			root.addEventListener("mousemove", (event) => {
				const x = (event.clientX / Math.max(window.innerWidth, 1) - 0.5) * 18;
				const y = (event.clientY / Math.max(window.innerHeight, 1) - 0.5) * 18;
				loginBackground.style.transform = `translate3d(${x}px, ${y}px, 0)`;
			});
		}
	};

	const bindAccountForms = () => {
		const profileForm = root.querySelector("[data-account-profile-form]");
		const passwordForm = root.querySelector("[data-account-password-form]");
		const logoutButton = root.querySelector("[data-account-logout-btn]");

		if (profileForm) {
			profileForm.addEventListener("submit", async (event) => {
				event.preventDefault();
				showMessage("");
				const formData = new FormData(profileForm);
				try {
					await callApi(
						"ecommerce.customer_api.customer_update_profile",
						Object.fromEntries(formData),
						"POST"
					);
					showMessage("Profile updated successfully.", "success");
					window.setTimeout(() => window.location.reload(), 600);
				} catch (error) {
					showMessage(error.message, "error");
				}
			});
		}

		if (passwordForm) {
			passwordForm.addEventListener("submit", async (event) => {
				event.preventDefault();
				showMessage("");
				const formData = new FormData(passwordForm);
				try {
					await callApi(
						"ecommerce.customer_api.customer_change_password",
						Object.fromEntries(formData),
						"POST"
					);
					showMessage("Password updated successfully.", "success");
					passwordForm.reset();
				} catch (error) {
					showMessage(error.message, "error");
				}
			});
		}

		if (logoutButton) {
			logoutButton.addEventListener("click", async () => {
				showMessage("");
				try {
					await callApi("ecommerce.customer_api.customer_logout", {}, "POST");
					window.location.href = "/customer-login";
				} catch (error) {
					showMessage(error.message, "error");
				}
			});
		}
	};

	const renderOrderDetails = (details) => {
		const escapeHtml = (value) =>
			String(value || "")
				.replaceAll("&", "&amp;")
				.replaceAll("<", "&lt;")
				.replaceAll(">", "&gt;")
				.replaceAll('"', "&quot;")
				.replaceAll("'", "&#39;");

		const order = details.order || {};
		const items = details.items || [];

		const rows = items
			.map(
				(item) => `
				<tr>
					<td>${escapeHtml(item.item_code)}</td>
					<td>${escapeHtml(item.item_name)}</td>
					<td>${escapeHtml(item.qty)} ${escapeHtml(item.uom)}</td>
					<td>${escapeHtml(item.formatted_rate || item.rate)}</td>
					<td>${escapeHtml(item.formatted_amount || item.amount)}</td>
				</tr>`
			)
			.join("");

		return `
			<div class="ec-order-detail-head">
				<p><strong>Order:</strong> ${escapeHtml(order.name)}</p>
				<p><strong>Status:</strong> ${escapeHtml(order.status || "-")}</p>
				<p><strong>Total:</strong> ${escapeHtml(order.formatted_total || order.total_amount || "")}</p>
			</div>
			<div class="ec-order-detail-table-wrap">
				<table class="ec-order-detail-table">
					<thead>
						<tr>
							<th>Item Code</th>
							<th>Item Name</th>
							<th>Qty</th>
							<th>Rate</th>
							<th>Amount</th>
						</tr>
					</thead>
					<tbody>${rows || "<tr><td colspan='5'>No items found.</td></tr>"}</tbody>
				</table>
			</div>`;
	};

	const bindOrderDetails = () => {
		const buttons = root.querySelectorAll("[data-order-detail-btn]");
		if (!buttons.length) return;

		buttons.forEach((button) => {
			button.addEventListener("click", async () => {
				const orderName = button.getAttribute("data-order-name");
				if (!orderName) return;

				const row = root.querySelector(`[data-order-detail-row="${orderName}"]`);
				const content = root.querySelector(`[data-order-detail-content="${orderName}"]`);
				if (!row || !content) return;

				if (!row.hidden) {
					row.hidden = true;
					return;
				}

				showMessage("");
				try {
					const details = await callApi(
						"ecommerce.customer_api.customer_order_details",
						{ order_name: orderName },
						"GET"
					);
					content.innerHTML = renderOrderDetails(details);
					row.hidden = false;
				} catch (error) {
					showMessage(error.message, "error");
				}
			});
		});
	};

	const bindCheckoutPage = () => {
		const checkoutForm = root.querySelector("[data-checkout-form]");
		const placeOrderButton = root.querySelector("[data-place-order-btn]");
		if (!checkoutForm || !placeOrderButton) return;

		const syncSelectedCards = (selector, cardSelector) => {
			root.querySelectorAll(selector).forEach((input) => {
				const card = input.closest(cardSelector);
				if (card) {
					card.classList.toggle("is-selected", input.checked);
				}
			});
		};

		root.addEventListener("change", (event) => {
			if (event.target.closest("[data-checkout-choice]")) {
				syncSelectedCards("[data-checkout-choice]", ".ec-checkout-choice");
			}
			if (event.target.closest("[data-checkout-payment]")) {
				syncSelectedCards("[data-checkout-payment]", ".ec-checkout-payment");
			}
		});

		const createAddressIfNeeded = async (formData) => {
			const savedShippingAddress = formData.get("shipping_address") || "";
			const savedBillingAddress = formData.get("billing_address") || savedShippingAddress;
			if (savedShippingAddress || savedBillingAddress) {
				return {
					billing_address: savedBillingAddress,
					shipping_address: savedShippingAddress || savedBillingAddress,
				};
			}

			const streetAddress = String(formData.get("street_address") || "").trim();
			const city = String(formData.get("city") || "").trim();
			if (!streetAddress || !city) {
				throw new Error("Shipping address and city are required.");
			}

			const addressTitle =
				String(formData.get("company_name") || "").trim() ||
				String(formData.get("full_name") || "").trim() ||
				"Checkout Address";

			const result = await callApi(
				"ecommerce.customer_api.customer_add_address",
				{
					address_title: addressTitle,
					address_type: "Shipping",
					address_line1: streetAddress,
					city,
					state: String(formData.get("state") || "").trim(),
					pincode: String(formData.get("zip") || "").trim(),
					phone: String(formData.get("phone") || "").trim(),
					email_id: String(formData.get("email") || "").trim(),
					is_shipping_address: 1,
				},
				"POST"
			);

			const addressName = result && result.address && result.address.name;
			return {
				billing_address: addressName || "",
				shipping_address: addressName || "",
			};
		};

		const buildCheckoutNotes = (formData) => {
			const lines = [
				`Shipping Method: ${formData.get("shipping_method") || "Standard (3-5 days)"}`,
				`Payment Method: ${formData.get("payment_method") || "Corporate Credit Card"}`,
				"",
				"Shipping Details:",
				`Company: ${formData.get("company_name") || ""}`,
				`Full Name: ${formData.get("full_name") || ""}`,
				`Street Address: ${formData.get("street_address") || ""}`,
				`City: ${formData.get("city") || ""}`,
				`State: ${formData.get("state") || ""}`,
				`Zip: ${formData.get("zip") || ""}`,
				`Phone: ${formData.get("phone") || ""}`,
			];
			return lines.join("\n");
		};

		placeOrderButton.addEventListener("click", async () => {
			showMessage("");
			if (!checkoutForm.reportValidity()) return;

			const originalHtml = placeOrderButton.innerHTML;
			placeOrderButton.disabled = true;
			placeOrderButton.innerHTML = "<span>Placing Order...</span>";
			showMessage("Placing your order...", "loading");

			try {
				const formData = new FormData(checkoutForm);
				const addresses = await createAddressIfNeeded(formData);
				const order = await callApi(
					"ecommerce.customer_api.checkout_place_order",
					{
						billing_address: addresses.billing_address || "",
						shipping_address: addresses.shipping_address || "",
						notes: buildCheckoutNotes(formData),
					},
					"POST"
				);
				showMessage(`Order ${order.order_name || ""} placed successfully.`, "success");
				window.setTimeout(() => {
					window.location.href = "/account";
				}, 900);
			} catch (error) {
				placeOrderButton.disabled = false;
				placeOrderButton.innerHTML = originalHtml;
				showMessage(error.message || "Unable to place order.", "error");
			}
		});
	};

	bindAuthForms();
	bindLoginDesignControls();
	bindAccountForms();
	bindOrderDetails();
	bindCheckoutPage();
})();
