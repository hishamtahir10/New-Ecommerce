# E-Commerce Order Processing System

Python Intern Real-World Assessment. Standard library only, no classes, only functions.

## Project structure

All files sit together in one folder (the project root; in a git repo they are at the repo root). Run the commands below from that folder, the one that contains `main.py`.

```
.
├── main.py          # entry point (demo + --test)
├── config.py        # all rule numbers in one SETTINGS dictionary
├── data.py          # starter products and orders
├── helpers.py       # add_up(*args), money()
├── pricing.py       # subtotal, discount (closure built once), shipping
├── validation.py    # validate_order() + price/stock checks
├── orders.py        # process_order(**options), process_all_orders(), mark_paid()
├── reports.py       # summary dictionary + formatted sales report
├── test_orders.py   # small test_ functions (plain Python or pytest)
├── .gitignore
├── README.md
└── VIVA_NOTES.md    # viva questions and answers
```

## Run

```
python main.py          # demo with starter data + sales report
python main.py --test   # run all tests (normal + edge cases)
python -m pytest        # optional, only if pytest is installed
```

(Use `python3` on Mac/Linux if needed. Python 3.6+. Run from inside this folder.)

## Business rules

- Discount: subtotal >= 1000 -> 15%, >= 500 -> 10%, >= 200 -> 5%, else 0%
- Shipping: subtotal >= 500 -> free, else $20 (based on the subtotal before discount)
- Order total = subtotal - discount + shipping
- Money uses `Decimal` and is rounded half up to cents (150.675 -> 150.68), never float rounding
- Only `paid` orders count as revenue; `pending` orders are valid but not counted
- Stock is reduced only for valid AND paid orders
- **Pending orders are provisional**: they do not reserve stock. Two pending orders for the
  last 10 laptops are both accepted as pending. To pay a pending order call `mark_paid(...)`
  (see "Paying a pending order" below): stock is checked again at that moment, so only the
  first one can be filled
- Low stock = stock <= 10
- All these numbers (tiers, shipping, low-stock limit) live in `config.py` -> `SETTINGS`
- Ties (top product / top customer) show all tied names

## Validation (an order is rejected when...)

- `order_id` or `customer` is missing, empty or not a string
- there are no items, or an item is malformed
- the product ID is unknown
- the product's `price` is not a number >= 0, or its `stock` is not a whole number >= 0
- quantity is not a whole number, or is zero / negative
- quantity (all lines of the same product added together) is more than the stock
- `payment_status` is not "paid" or "pending"
- the same `order_id` was already accepted ("Duplicate order ID ..."). IDs are compared ignoring
  spaces and case ("ord009 " = "ORD009") and are stored as upper case

Customer names are compared ignoring spaces and upper/lower case ("Ali" and "ali " are one customer).
The report line "Customers With A Valid Order" counts customers with a paid OR pending order
(not only paying customers); rejected orders are never counted.

## Options

`process_order(order, products, seen_ids=None, include_shipping=True, apply_discount=True)`
`process_all_orders(orders, products, include_shipping=True, apply_discount=True)`

- `include_shipping=False` -> no shipping is charged
- `apply_discount=False` -> no discount is applied
- `seen_ids` (optional set): when given, an already accepted order ID is rejected as a duplicate.
  `process_all_orders` creates one set and passes it to every `process_order` call, so the
  duplicate rule lives in one place.
- Only these two names are allowed and both must be `True` / `False`.
  A misspelt name or a wrong type (for example `apply_discount="no"`) raises `TypeError`.

## Errors in the input

- `process_all_orders` raises `TypeError` if `orders` is not a list or `products` is not a dict.
- A bad single order never crashes the run: it is returned as `rejected` with a reason,
  and the record keeps its order ID.

## Paying a pending order

```python
processed = process_all_orders(orders, products)              # ORD003 is pending
record = mark_paid("ORD003", processed, products)            # pay it later
```

- `mark_paid(order_id, processed_orders, products)` finds the order (ID ignoring case/spaces),
  checks the stock again, reduces it and changes the status to `paid` (it now counts as revenue).
- If the stock is not enough any more, nothing changes: the order stays `pending` and
  `record["reason"]` says why (for example "Payment not completed: Insufficient stock for P001 ...").
- It uses the prices saved in the record, so a later price change does not matter.
- It raises `ValueError` if there is no pending order with that ID (unknown, already paid or
  rejected), so an order can never be paid twice and stock is never reduced twice.

## Order record

`process_order` returns one dictionary per order: `order_id`, `customer`, `status`
(`paid` / `pending` / `rejected`), `items`, `subtotal`, `discount`, `shipping`, `total`, `reason`.
Each entry in `items` keeps what was sold and at which price, so the record is complete on its own
(the product's price may change later):

```
{"product_id": "P001", "quantity": 1, "unit_price": Decimal("1200.00"), "line_total": Decimal("1200.00")}
```

## Sample output (`python main.py`)

```
Order log:
  ORD001 (Ali): PAID | subtotal $1,250.00, discount $187.50, shipping $0.00, total $1,062.50
  ORD002 (Ahmed): PAID | subtotal $450.00, discount $22.50, shipping $20.00, total $447.50
  ORD003 (Ali): PENDING | subtotal $125.00, discount $0.00, shipping $20.00, total $145.00

========== SALES REPORT ==========

Total Orders: 3
Paid Orders: 2
Pending Orders: 1
Rejected Orders: 0

Total Revenue: $1,510.00
Total Discount: $210.00
Total Shipping: $20.00

Customers With A Valid Order: 2
Top Customer: Ali ($1,062.50)
Top Selling Product: Keyboard, Mouse (tie, 2 units each)
Categories Sold: Accessories, Electronics

Low Stock Products:
- Laptop (P001): 9 left

==================================
```

## Assumptions

- **Shipping** is decided on the subtotal BEFORE discount (520 -> discount 52 -> shipping free -> total 468).
- **Revenue** = what customers paid (subtotal - discount + shipping) of PAID orders only.
- **Pending orders** are checked against the current stock (more than the stock is rejected),
  but they do not reserve stock and do not count as revenue. Stock is checked again when
  `mark_paid()` pays the order, so two pending orders for the last items can both be accepted
  and only one paid. Sending the same ID again as "paid" is NOT the way to pay: it is rejected
  as a duplicate.
- **Ties**: if customers or products tie for first place, all tied names are shown
  (customers and products are listed A-Z).
- **Duplicate IDs**: an order ID can be accepted once (ignoring case/spaces). An ID whose first
  order was rejected may be sent again after fixing the problem.
- **products is changed in place**: paid orders reduce its stock. Running the processing twice on
  the same dictionary uses the already reduced stock; pass `copy.deepcopy(products)` to keep the original.
- **Reports**: `build_sales_summary()` returns a dictionary (easy to test), `format_sales_report()`
  turns it into text, and only `main.py` prints.
