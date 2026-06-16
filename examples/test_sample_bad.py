"""
功能正确性测试 - 用于 OpenEvolve 的硬门控评估

这些测试定义了 process_orders / find_duplicates / calculate_discount 的"正确行为"。
OpenEvolve 进化出的任何代码变体都必须通过这些测试，否则直接淘汰。
"""

import pytest
from sample_bad import process_orders, find_duplicates, calculate_discount, Order


class TestProcessOrders:
    def test_empty_list(self):
        result = process_orders([])
        assert result == {"processed": 0, "failed": 0, "total_revenue": 0.0, "by_status": {}}

    def test_single_valid_order(self):
        order = Order(
            order_id="ORD-001",
            customer_name="Alice",
            items=[{"sku": "A1", "qty": 2}],
            total=100.0,
            status="pending",
        )
        result = process_orders([order])
        assert result["processed"] == 1
        assert result["failed"] == 0
        assert result["total_revenue"] == 100.0

    def test_missing_order_id(self):
        order = Order(
            order_id="",
            customer_name="Bob",
            items=[{"sku": "B1", "qty": 1}],
            total=50.0,
            status="pending",
        )
        result = process_orders([order])
        assert result["failed"] == 1
        assert result["processed"] == 0

    def test_negative_total(self):
        order = Order(
            order_id="ORD-002", customer_name="Charlie",
            items=[{"sku": "C1", "qty": 1}],
            total=-10.0, status="pending",
        )
        result = process_orders([order])
        assert result["failed"] == 1

    def test_invalid_status(self):
        order = Order(
            order_id="ORD-003", customer_name="Dave",
            items=[{"sku": "D1", "qty": 1}],
            total=200.0, status="unknown_status",
        )
        result = process_orders([order])
        assert result["failed"] == 1

    def test_shipping_required_for_shipped(self):
        order = Order(
            order_id="ORD-004", customer_name="Eve",
            items=[{"sku": "E1", "qty": 1}],
            total=300.0, status="shipped", shipping_address=None,
        )
        result = process_orders([order])
        assert result["failed"] == 1

    def test_payment_required_for_confirmed(self):
        order = Order(
            order_id="ORD-005", customer_name="Frank",
            items=[{"sku": "F1", "qty": 1}],
            total=400.0, status="confirmed", payment_method=None,
        )
        result = process_orders([order])
        assert result["failed"] == 1

    def test_discount_code_vip10(self):
        order = Order(
            order_id="ORD-006", customer_name="Grace",
            items=[{"sku": "G1", "qty": 1}],
            total=200.0, status="pending", discount_code="VIP10",
        )
        result = process_orders([order])
        assert result["processed"] == 1
        assert result["total_revenue"] == pytest.approx(180.0)  # 10% off

    def test_discount_code_summer20(self):
        order = Order(
            order_id="ORD-007", customer_name="Hank",
            items=[{"sku": "H1", "qty": 1}],
            total=500.0, status="pending", discount_code="SUMMER20",
        )
        result = process_orders([order])
        assert result["processed"] == 1
        assert result["total_revenue"] == pytest.approx(400.0)  # 20% off

    def test_high_value_discount(self):
        """total > 1000 should get at least 5% discount"""
        order = Order(
            order_id="ORD-008", customer_name="Ivy",
            items=[{"sku": "I1", "qty": 10}],
            total=2000.0, status="pending",
        )
        result = process_orders([order])
        assert result["processed"] == 1
        assert result["total_revenue"] <= 1900.0  # at least 5% off

    def test_very_high_value_discount(self):
        """total > 5000 should get at least 10% discount"""
        order = Order(
            order_id="ORD-009", customer_name="Jack",
            items=[{"sku": "J1", "qty": 100}],
            total=6000.0, status="pending",
        )
        result = process_orders([order])
        assert result["processed"] == 1
        assert result["total_revenue"] <= 5400.0  # at least 10% off

    def test_by_status_aggregation(self):
        orders = [
            Order(order_id="1", customer_name="A", items=[{"sku": "X"}], total=100.0, status="pending"),
            Order(order_id="2", customer_name="B", items=[{"sku": "Y"}], total=200.0, status="pending"),
            Order(order_id="3", customer_name="C", items=[{"sku": "Z"}], total=300.0, status="confirmed", payment_method="card"),
        ]
        result = process_orders(orders)
        assert result["by_status"]["pending"]["count"] == 2
        assert result["by_status"]["pending"]["revenue"] == 300.0
        assert result["by_status"]["confirmed"]["count"] == 1

    def test_mixed_valid_invalid(self):
        orders = [
            Order(order_id="1", customer_name="A", items=[{"sku": "X"}], total=100.0, status="pending"),
            Order(order_id="", customer_name="B", items=[{"sku": "Y"}], total=50.0, status="pending"),  # invalid
            Order(order_id="2", customer_name="C", items=[{"sku": "Z"}], total=200.0, status="confirmed", payment_method="card"),
        ]
        result = process_orders(orders)
        assert result["processed"] == 2
        assert result["failed"] == 1


class TestFindDuplicates:
    def test_empty(self):
        assert find_duplicates([]) == []

    def test_no_duplicates(self):
        assert find_duplicates(["a", "b", "c"]) == []

    def test_has_duplicates(self):
        result = find_duplicates(["a", "b", "a", "c", "b", "b"])
        assert sorted(result) == ["a", "b"]

    def test_all_same(self):
        result = find_duplicates(["x", "x", "x"])
        assert result == ["x"]

    def test_single_item(self):
        assert find_duplicates(["only"]) == []


class TestCalculateDiscount:
    def test_vip_old(self):
        assert calculate_discount(100.0, "vip", 6) == 0.15

    def test_vip_medium(self):
        assert calculate_discount(100.0, "vip", 3) == 0.10

    def test_vip_new(self):
        assert calculate_discount(100.0, "vip", 1) == 0.05

    def test_regular_high_value_old(self):
        assert calculate_discount(2000.0, "regular", 5) == 0.08

    def test_regular_high_value_new(self):
        assert calculate_discount(2000.0, "regular", 2) == 0.05

    def test_regular_low_value_old(self):
        assert calculate_discount(500.0, "regular", 4) == 0.03

    def test_regular_low_value_new(self):
        assert calculate_discount(500.0, "regular", 1) == 0.0

    def test_new_customer_high_value(self):
        assert calculate_discount(600.0, "new", 0) == 0.03

    def test_new_customer_low_value(self):
        assert calculate_discount(100.0, "new", 0) == 0.0

    def test_unknown_type(self):
        """Unrecognized customer_type gets no discount (current behavior)"""
        assert calculate_discount(1000.0, "unknown", 5) == 0.0
