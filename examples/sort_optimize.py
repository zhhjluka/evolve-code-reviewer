"""
排序算法优化样本 — O(n²) bubble sort → 进化目标: O(n log n)
"""

# EVOLVE-BLOCK-START
def sort_scores(scores: list[int]) -> list[int]:
    """冒泡排序 — O(n²)，应进化为更高效的算法"""
    arr = scores[:]  # 不影响原数组
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(n - 1 - i):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr
# EVOLVE-BLOCK-END


# EVOLVE-BLOCK-START
def find_top_n(scores: list[int], n: int) -> list[int]:
    """找前 N 名 — O(k*n)，每次循环扫描全列表"""
    result = []
    remaining = scores[:]
    for _ in range(min(n, len(scores))):
        if not remaining:
            break
        best_idx = 0
        for i in range(1, len(remaining)):
            if remaining[i] > remaining[best_idx]:
                best_idx = i
        result.append(remaining.pop(best_idx))
    return result
# EVOLVE-BLOCK-END
