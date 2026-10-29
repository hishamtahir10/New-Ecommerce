"""orders.py - processes orders: validation, pricing, payment status, inventory update.

PENDING ORDERS (important rule):
    A pending order is only PROVISIONAL. It is validated, but it does not
    reserve stock and it does not count as revenue. To pay it later, call
    mark_paid(order_id, processed_orders, products): the stock is checked
    AGAIN at that moment, so two pending orders for the same last items can
    both be accepted, but only one of them can be paid.
    (Sending the same order ID again as "paid" is a duplicate and is rejected.)
"""

from validation import validate_order, is_non_empty_string, is_valid_stock
from pricing import calculate_order_subtotal, calculate_discount, calculate_shipping
from helpers import round_money, to_decimal


def check_options(options):
    """Reject misspelt option names and non-boolean values (a typo must not be ignored silently)."""
    unknown = set(options) - {"include_shipping", "apply_discount"}
    if unknown:
        raise TypeError(f"Unknown option(s): {sorted(unknown)}")
    for name, value in options.items():
        if not isinstance(value, bool):
            raise TypeError(f"Option '{name}' must be True or False, got {value!r}")


def get_order_key(order):
    """Normalised order ID used for duplicate checks: spaces removed, UPPER CASE.
    "ord009 " and "ORD009" are the same order. None if the ID is missing/invalid."""
    order_id = order.get("order_id") if isinstance(order, dict) else None
    return order_id.strip().upper() if is_non_empty_string(order_id) else None


def build_record(order, status="rejected", reason=""):
    """Empty result record. Keeps the (normalised) order ID / customer when they are
    usable, so even a failed order can be identified in the report."""
    safe_order = order if isinstance(order, dict) else {}
    customer = safe_order.get("customer")
    return {
        "order_id": get_order_key(order) or "UNKNOWN",
        "customer": customer.strip() if is_non_empty_string(customer) else "Unknown",
        "status": status,
        "items": [],
        "subtotal": round_money(0),
        "discount": round_money(0),
        "shipping": round_money(0),
        "total": round_money(0),
        "reason": reason,
    }


def process_order(order, products, seen_ids=None, **options):
    """Process ONE order and return a result record (a dictionary).

    seen_ids (optional set): IDs of orders already accepted. If given, an order whose
        ID is already in it is rejected as a duplicate (no double charge), and every
        accepted order adds its ID to it. This is the ONE place where the rule lives;
        process_all_orders simply passes the same set to every call.
        Without seen_ids there is no duplicate protection.

    Options (**kwargs, must be True/False, unknown names raise TypeError):
        include_shipping=True  -> add shipping cost (False = no shipping charged)
        apply_discount=True    -> apply the discount slab (False = no discount)

    status in the result is: "paid", "pending" or "rejected".
    Stock is reduced ONLY when the order is valid AND paid (pending = provisional).
    """
    check_options(options)
    if seen_ids is not None and not isinstance(seen_ids, set):
        raise TypeError("seen_ids must be a set")
    include_shipping = options.get("include_shipping", True)
    apply_discount = options.get("apply_discount", True)

    record = build_record(order)
    order_key = get_order_key(order)

    if seen_ids is not None and order_key in seen_ids:
        record["reason"] = f"Duplicate order ID {order_key}"
        return record

    is_valid, reason = validate_order(order, products)
    if not is_valid:
        record["reason"] = reason
        return record

    subtotal = calculate_order_subtotal(order, products)
    discount = calculate_discount(subtotal) if apply_discount else round_money(0)
    shipping = calculate_shipping(subtotal) if include_shipping else round_money(0)

    # Each line keeps the price it was sold at, so the order record is complete on its own
    # (the product's price may change later). line_total = unit_price x quantity.
    record["items"] = [
        {
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "unit_price": round_money(products[item["product_id"]]["price"]),
            "line_total": round_money(to_decimal(products[item["product_id"]]["price"]) * item["quantity"]),
        }
        for item in order["items"]
    ]
    record["subtotal"] = subtotal
    record["discount"] = discount
    record["shipping"] = shipping
    record["total"] = round_money(subtotal - discount + shipping)
    record["status"] = order["payment_status"]  # "paid" or "pending"

    if record["status"] == "paid":
        for item in order["items"]:
            products[item["product_id"]]["stock"] -= item["quantity"]

    if seen_ids is not None:
        seen_ids.add(order_key)   # remembered only AFTER the order was accepted
    return record


def process_all_orders(orders, products, **options):
    """Process orders one by one (in order) and collect the results.

    - The same order ID (ignoring case and spaces) is accepted only ONCE: a repeat
      is rejected with "Duplicate order ID ...". An ID whose first order was
      rejected may be submitted again (e.g. after fixing the quantity).
    - A crash in one order never stops the others, and the record keeps its order ID.
    - NOTE: `products` is changed IN PLACE (stock goes down for paid orders). Running this
      twice on the same dictionary uses the already reduced stock. To keep the original,
      pass a copy: process_all_orders(orders, copy.deepcopy(products)).
    """
    if not isinstance(orders, (list, tuple)):
        raise TypeError("orders must be a list of order dictionaries")
    if not isinstance(products, dict):
        raise TypeError("products must be a dictionary")
    check_options(options)  # fail early, once, instead of once per order

    processed = []
    seen_ids = set()
    for order in orders:
        try:
            record = process_order(order, products, seen_ids, **options)
        except Exception as error:  # safety net - should not normally happen
            record = build_record(order, reason="Unexpected error: " + str(error))
        processed.append(record)
    return processed


def mark_paid(order_id, processed_orders, products):
    """Pay a PENDING order that was already processed. Returns the updated record.

    - The order is found by ID (ignoring case and spaces) in `processed_orders`,
      the list returned by process_all_orders.
    - Stock is checked AGAIN now. If there is enough, stock is reduced and the
      status becomes "paid" (it now counts as revenue).
    - If there is not enough stock any more, NOTHING changes: the order stays
      "pending" and record["reason"] explains why.
    - The prices saved in the record (unit_price / line_total) are used, so a
      later price change does not matter.
    - Raises ValueError if there is no PENDING order with that ID (unknown ID,
      already paid, or rejected). So an order can never be paid twice and stock
      can never be reduced twice.
    """
    if not isinstance(processed_orders, (list, tuple)):
        raise TypeError("processed_orders must be a list of order records")
    if not isinstance(products, dict):
        raise TypeError("products must be a dictionary")
    if not is_non_empty_string(order_id):
        raise ValueError("order_id must be a non-empty string")

    key = order_id.strip().upper()
    matches = [r for r in processed_orders if isinstance(r, dict) and r.get("order_id") == key]
    if not matches:
        raise ValueError(f"No order with ID {key}")
    pending = [r for r in matches if r["status"] == "pending"]
    if not pending:
        statuses = ", ".join(sorted({r["status"] for r in matches}))
        raise ValueError(f"Order {key} is not pending (status: {statuses})")
    record = pending[0]

    needed = {}   # product_id -> total quantity of this order
    for line in record["items"]:
        needed[line["product_id"]] = needed.get(line["product_id"], 0) + line["quantity"]

    for product_id, quantity in needed.items():
        product = products.get(product_id)
        if not isinstance(product, dict) or not is_valid_stock(product.get("stock")):
            record["reason"] = f"Payment not completed: product {product_id} is not available"
            return record
        if quantity > product["stock"]:
            record["reason"] = (f"Payment not completed: Insufficient stock for {product_id} "
                                f"(wanted {quantity}, have {product['stock']})")
            return record

    for product_id, quantity in needed.items():
        products[product_id]["stock"] -= quantity
    record["status"] = "paid"
    record["reason"] = ""
    return record
