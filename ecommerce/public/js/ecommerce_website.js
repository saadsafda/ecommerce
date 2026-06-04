(() => {
	const getCookie = (name) => {
		const parts = (`; ${document.cookie}`).split(`; ${name}=`);
		if (parts.length === 2) return parts.pop().split(";").shift();
		return "";
	};

	const normalizeToken = (value) => {
		const token = String(value || "").trim();
		return ["", "none", "null", "undefined"].includes(token.toLowerCase()) ? "" : token;
	};

	const getCsrfToken = () =>
		normalizeToken(
			window.csrf_token ||
				(window.frappe && (frappe.csrf_token || (frappe.boot && frappe.boot.csrf_token))) ||
				getCookie("csrf_token")
		);

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
		} catch (error) {
			throw new Error("Unexpected server response.");
		}

		if (!response.ok || payload.exc) {
			throw new Error(payload.message || "Cart request failed.");
		}

		return payload.message;
	};

	const updateCartBadges = (count) => {
		document.querySelectorAll("[data-cart-badge-count]").forEach((badge) => {
			badge.textContent = String(count || 0);
		});
	};

	const setText = (selector, value) => {
		if (value === undefined || value === null) return;
		document.querySelectorAll(selector).forEach((element) => {
			element.textContent = String(value);
		});
	};

	const findCartRow = (itemCode) =>
		Array.from(document.querySelectorAll("[data-cart-row]")).find(
			(row) => row.getAttribute("data-cart-row") === String(itemCode)
		);

	const findCartItem = (cart, itemCode) => {
		const items = cart && Array.isArray(cart.items) ? cart.items : [];
		return items.find((item) => String(item.item_code) === String(itemCode));
	};

	const updateCartSummary = (cart) => {
		if (!cart) return;
		updateCartBadges(cart.item_count);
		setText("[data-cart-subtotal]", cart.formatted_subtotal);
		setText("[data-cart-shipping]", cart.formatted_shipping_estimate);
		setText("[data-cart-tax]", cart.formatted_tax_amount);
		setText("[data-cart-grand-total]", cart.formatted_grand_total);
	};

	const setCartRowBusy = (row, busy) => {
		if (!row) return;
		row.classList.toggle("is-loading", busy);
		row.querySelectorAll("button, input").forEach((control) => {
			control.disabled = busy;
		});
	};

	const refreshCartRow = (itemCode, cart) => {
		const row = findCartRow(itemCode);
		if (!row) return;

		const cartItem = findCartItem(cart, itemCode);
		if (!cartItem) {
			row.remove();
			return;
		}

		const qtyInput = row.querySelector("[data-qty-input]");
		const lineTotal = row.querySelector("[data-line-total]");
		if (qtyInput) {
			qtyInput.value = String(cartItem.qty || 1);
			qtyInput.defaultValue = String(cartItem.qty || 1);
		}
		if (lineTotal) lineTotal.textContent = cartItem.formatted_line_total || "";
	};

	const reloadCartIfEmpty = (cart) => {
		if (document.querySelector("[data-cart-page]") && cart && !cart.item_count) {
			window.location.reload();
			return true;
		}
		return false;
	};

	let cartActionsBound = false;

	const setCartFeedback = (button, message = "", type = "success") => {
		const scope = button.closest(".ec-product-actions, .ec-product-card");
		const feedback = scope ? scope.querySelector("[data-cart-feedback]") : null;
		if (!feedback) return;

		feedback.textContent = message;
		feedback.className = message ? `ec-cart-feedback is-${type}` : "ec-cart-feedback";
		if (message) {
			window.clearTimeout(feedback.ecTimer);
			feedback.ecTimer = window.setTimeout(() => {
				feedback.textContent = "";
				feedback.className = "ec-cart-feedback";
			}, 4200);
		}
	};

	/* ─── Mobile Menu ─── */
	const initMobileMenu = () => {
		const toggle = document.querySelector("[data-mobile-menu-toggle]");
		const menu = document.querySelector("[data-mobile-menu]");
		if (!toggle || !menu) return;

		toggle.addEventListener("click", () => {
			menu.classList.toggle("is-open");
		});
	};

	/* ─── Hero Slider ─── */
	const initSlider = () => {
		const slider = document.querySelector("[data-ecom-slider]");
		if (!slider) return;

		const slides = Array.from(slider.querySelectorAll("[data-slide]"));
		const dots = Array.from(slider.querySelectorAll("[data-slide-trigger]"));
		if (slides.length <= 1) return;

		let activeIndex = 0;
		let timer = null;

		const setActiveSlide = (index) => {
			activeIndex = index;
			slides.forEach((slide, idx) => {
				slide.classList.toggle("is-active", idx === index);
			});
			dots.forEach((dot, idx) => {
				dot.classList.toggle("is-active", idx === index);
			});
		};

		const moveNext = () => {
			const nextIndex = (activeIndex + 1) % slides.length;
			setActiveSlide(nextIndex);
		};

		const restartTimer = () => {
			if (timer) {
				clearInterval(timer);
			}
			timer = setInterval(moveNext, 5000);
		};

		dots.forEach((dot, index) => {
			dot.addEventListener("click", () => {
				setActiveSlide(index);
				restartTimer();
			});
		});

		restartTimer();
	};

	/* ─── Mobile Nav Highlight ─── */
	const highlightMobileNav = () => {
		const path = window.location.pathname;
		const links = document.querySelectorAll(".ec-mobile-bottom-nav a");
		links.forEach((link) => {
			const href = link.getAttribute("href");
			const isActive = href === "/" ? path === "/" : path.startsWith(href);
			link.classList.toggle("is-active", isActive);
		});
	};

	/* ─── Scroll Reveal (IntersectionObserver) ─── */
	const initScrollReveal = () => {
		const elements = document.querySelectorAll(".ec-reveal");
		if (!elements.length) return;

		const observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting) {
						// Stagger delay for product cards within a grid
						const parent = entry.target.parentElement;
						if (parent && parent.classList.contains("ec-product-grid")) {
							const siblings = Array.from(
								parent.querySelectorAll(".ec-reveal:not(.ec-revealed)")
							);
							const idx = siblings.indexOf(entry.target);
							entry.target.style.transitionDelay = `${Math.max(0, idx) * 80}ms`;
						}
						entry.target.classList.add("ec-revealed");
						observer.unobserve(entry.target);
					}
				});
			},
			{
				threshold: 0.08,
				rootMargin: "0px 0px -40px 0px",
			}
		);

		elements.forEach((el) => observer.observe(el));
	};

	/* ─── Sticky Navbar Blur on Scroll ─── */
	const initNavbarScroll = () => {
		const navbar = document.querySelector(".ec-navbar-shell");
		if (!navbar) return;

		let ticking = false;
		const scrollThreshold = 50;

		const handleScroll = () => {
			if (!ticking) {
				requestAnimationFrame(() => {
					if (window.scrollY > scrollThreshold) {
						navbar.classList.add("ec-navbar-scrolled");
					} else {
						navbar.classList.remove("ec-navbar-scrolled");
					}
					ticking = false;
				});
				ticking = true;
			}
		};

		window.addEventListener("scroll", handleScroll, { passive: true });
		// Check initial state
		handleScroll();
	};

	/* ─── Cart Actions ─── */
	const initCartActions = () => {
		if (cartActionsBound) return;
		cartActionsBound = true;

		callApi("ecommerce.customer_api.cart_count", {}, "GET")
			.then((result) => updateCartBadges(result && result.count))
			.catch(() => {});

		document.addEventListener("click", async (event) => {
			const qtyControl = event.target.closest("[data-product-qty-minus], [data-product-qty-plus]");
			if (qtyControl) {
				event.preventDefault();
				const group = qtyControl.closest(".ec-qty-stepper");
				const input = group ? group.querySelector("[data-product-qty]") : null;
				if (!input) return;

				const current = Math.max(parseInt(input.value || "1", 10) || 1, 1);
				const next = qtyControl.hasAttribute("data-product-qty-minus")
					? Math.max(current - 1, 1)
					: current + 1;
				input.value = String(next);
				input.dispatchEvent(new Event("change", { bubbles: true }));
				return;
			}

			const cartQtyControl = event.target.closest("[data-qty-minus], [data-qty-plus]");
			if (cartQtyControl) {
				event.preventDefault();
				const itemCode = cartQtyControl.getAttribute("data-item");
				const row = findCartRow(itemCode);
				const input = row ? row.querySelector("[data-qty-input]") : null;
				if (!itemCode || !input) return;

				const current = Math.max(parseInt(input.value || "1", 10) || 1, 1);
				const next = cartQtyControl.hasAttribute("data-qty-minus")
					? Math.max(current - 1, 1)
					: current + 1;
				if (next === current) return;

				setCartRowBusy(row, true);
				try {
					const cart = await callApi(
						"ecommerce.customer_api.cart_update",
						{ item_code: itemCode, qty: next },
						"POST"
					);
					updateCartSummary(cart);
					refreshCartRow(itemCode, cart);
					if (!reloadCartIfEmpty(cart)) setCartRowBusy(row, false);
				} catch (error) {
					console.error(error);
					setCartRowBusy(row, false);
					input.value = String(current);
				}
				return;
			}

			const removeButton = event.target.closest("[data-cart-remove]");
			if (removeButton) {
				event.preventDefault();
				const itemCode = removeButton.getAttribute("data-cart-remove");
				const row = findCartRow(itemCode);
				if (!itemCode || !row) return;

				setCartRowBusy(row, true);
				try {
					const cart = await callApi(
						"ecommerce.customer_api.cart_remove",
						{ item_code: itemCode },
						"POST"
					);
					updateCartSummary(cart);
					refreshCartRow(itemCode, cart);
					reloadCartIfEmpty(cart);
				} catch (error) {
					console.error(error);
					setCartRowBusy(row, false);
				}
				return;
			}

			const clearButton = event.target.closest("[data-cart-clear]");
			if (clearButton) {
				event.preventDefault();
				if (clearButton.disabled) return;

				clearButton.disabled = true;
				try {
					const cart = await callApi("ecommerce.customer_api.cart_clear", {}, "POST");
					updateCartSummary(cart);
					if (!reloadCartIfEmpty(cart)) window.location.reload();
				} catch (error) {
					console.error(error);
					clearButton.disabled = false;
				}
				return;
			}

			const button = event.target.closest("[data-add-to-cart]");
			if (!button) return;

			event.preventDefault();
			event.stopPropagation();

			const itemCode = button.getAttribute("data-add-to-cart");
			if (!itemCode || button.disabled) return;

			const cardOrGroup = button.closest(".ec-product-card, .ec-add-to-cart-group, .ec-product-actions");
			const qtyInput = cardOrGroup ? cardOrGroup.querySelector("[data-product-qty]") : null;
			const qty = Math.max(parseInt((qtyInput && qtyInput.value) || "1", 10) || 1, 1);
			const originalHtml = button.innerHTML;

			button.disabled = true;
			button.classList.add("is-loading");
			setCartFeedback(button, "Adding item to cart...", "loading");
			button.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">hourglass_empty</span>';

			try {
				const cart = await callApi("ecommerce.customer_api.cart_add", { item_code: itemCode, qty }, "POST");
				updateCartBadges(cart && cart.item_count);
				button.classList.remove("is-loading");
				button.classList.add("is-added");
				setCartFeedback(button, `Added ${qty} item${qty > 1 ? "s" : ""} to cart.`, "success");
				button.innerHTML =
					'<span class="material-symbols-outlined" aria-hidden="true">check</span><span>Added</span>';
				window.setTimeout(() => {
					button.disabled = false;
					button.classList.remove("is-added");
					button.innerHTML = originalHtml;
				}, 1800);
			} catch (error) {
				console.error(error);
				button.disabled = false;
				button.classList.remove("is-loading");
				button.classList.add("is-error");
				button.title = error.message || "Unable to add item to cart.";
				setCartFeedback(button, button.title, "error");
				button.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">error</span>';
				window.setTimeout(() => {
					button.classList.remove("is-error");
					button.innerHTML = originalHtml;
				}, 1600);
			}
		});

		document.addEventListener("change", async (event) => {
			const input = event.target.closest("[data-qty-input]");
			if (!input) return;

			const itemCode = input.getAttribute("data-item");
			const row = findCartRow(itemCode);
			if (!itemCode || !row) return;

			const current = Math.max(parseInt(input.defaultValue || "1", 10) || 1, 1);
			const next = Math.max(parseInt(input.value || "1", 10) || 1, 1);
			input.value = String(next);
			if (next === current) return;

			setCartRowBusy(row, true);
			try {
				const cart = await callApi(
					"ecommerce.customer_api.cart_update",
					{ item_code: itemCode, qty: next },
					"POST"
				);
				updateCartSummary(cart);
				refreshCartRow(itemCode, cart);
				input.defaultValue = String(next);
				if (!reloadCartIfEmpty(cart)) setCartRowBusy(row, false);
			} catch (error) {
				console.error(error);
				input.value = String(current);
				setCartRowBusy(row, false);
			}
		});
	};

	/* ─── Init All ─── */
	const bootWebsite = () => {
		initMobileMenu();
		initSlider();
		highlightMobileNav();
		initScrollReveal();
		initNavbarScroll();
		initCartActions();
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", bootWebsite, { once: true });
	} else {
		bootWebsite();
	}
})();
