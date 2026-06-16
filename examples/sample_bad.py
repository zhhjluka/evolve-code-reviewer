"""
示例：需要被优化的"坏代码" - 高复杂度 + 性能差

这个文件模拟真实项目中常见的代码问题：
- process_orders: 上帝函数，圈复杂度 ~25，120 行
- find_duplicates: O(n²) 算法
- calculate_discount: 魔法数字 + 嵌套条件
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    order_id: str
    customer_name: str
    items: list[dict]
    total: float
    status: str
    discount_code: Optional[str] = None
    shipping_address: Optional[str] = None
    payment_method: Optional[str] = None


# EVOLVE-BLOCK-START
def process_orders(orders: list[Order]) -> dict:
    """
    处理订单列表。
    问题：圈复杂度 > 20，函数过长（~80 行），单一大函数包含校验+计算+分类+汇总。
    """
    result = {"processed": 0, "failed": 0, "total_revenue": 0.0, "by_status": {}}
    valid_statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]

    for order in orders:
        # --- 校验逻辑 (L25-L40) ---
        errors = []
        if not order.order_id:
            errors.append("missing order_id")
        if not order.customer_name:
            errors.append("missing customer_name")
        if not order.items:
            errors.append("no items")
        if order.total < 0:
            errors.append("negative total")
        if order.status not in valid_statuses:
            errors.append(f"invalid status: {order.status}")
        if order.shipping_address is None and order.status in ("shipped", "delivered"):
            errors.append("shipping_address required for shipped/delivered orders")
        if order.payment_method is None and order.status in ("confirmed", "shipped"):
            errors.append("payment_method required for confirmed/shipped orders")

        if errors:
            result["failed"] += 1
            continue

        # --- 折扣计算 (L43-L58) ---
        discount = 0.0
        if order.discount_code:
            if order.discount_code == "VIP10":
                discount = 0.10
            elif order.discount_code == "SUMMER20":
                discount = 0.20
            elif order.discount_code == "NEWUSER5":
                discount = 0.05
            elif order.discount_code.startswith("FLASH"):
                discount = 0.15
            else:
                discount = 0.0
        if order.total > 1000:
            discount = max(discount, 0.05)
        if order.total > 5000:
            discount = max(discount, 0.10)

        final_total = order.total * (1 - discount)

        # --- 分类汇总 (L61-L75) ---
        if order.status not in result["by_status"]:
            result["by_status"][order.status] = {"count": 0, "revenue": 0.0}
        result["by_status"][order.status]["count"] += 1
        result["by_status"][order.status]["revenue"] += final_total

        result["processed"] += 1
        result["total_revenue"] += final_total

    return result
# EVOLVE-BLOCK-END


# EVOLVE-BLOCK-START
def find_duplicates(items: list[str]) -> list[str]:
    """
    找出列表中的重复项。
    问题：O(n²) 时间复杂度。
    """
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j] and items[i] not in duplicates:
                duplicates.append(items[i])
    return duplicates
# EVOLVE-BLOCK-END


# EVOLVE-BLOCK-START
def calculate_discount(order_total: float, customer_type: str, years: int) -> float:
    """
    计算折扣。
    问题：嵌套 if-else + 魔法数字。
    """
    discount = 0.0
    if customer_type == "vip":
        if years > 5:
            discount = 0.15
        elif years > 2:
            discount = 0.10
        else:
            discount = 0.05
    elif customer_type == "regular":
        if order_total > 1000:
            if years > 3:
                discount = 0.08
            else:
                discount = 0.05
        else:
            if years > 3:
                discount = 0.03
            else:
                discount = 0.0
    elif customer_type == "new":
        if order_total > 500:
            discount = 0.03
        else:
            discount = 0.0
    return discount
# EVOLVE-BLOCK-END
