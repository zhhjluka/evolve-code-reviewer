"""功能正确性测试 — sort_optimize.py"""
import pytest
from sort_optimize import sort_scores, find_top_n


class TestSortScores:
    def test_empty(self):
        assert sort_scores([]) == []

    def test_single(self):
        assert sort_scores([5]) == [5]

    def test_sorted(self):
        assert sort_scores([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_reverse(self):
        assert sort_scores([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]

    def test_duplicates(self):
        assert sort_scores([3, 1, 2, 1, 3]) == [1, 1, 2, 3, 3]

    def test_negative(self):
        assert sort_scores([-3, 5, 0, -8, 2]) == [-8, -3, 0, 2, 5]

    def test_large(self):
        import random
        random.seed(42)
        data = [random.randint(0, 1000) for _ in range(200)]
        original = data[:]
        result = sort_scores(data)
        assert result == sorted(data)
        assert data == original  # 原始数据未被修改


class TestFindTopN:
    def test_empty(self):
        assert find_top_n([], 3) == []

    def test_n_larger_than_list(self):
        result = find_top_n([10, 20, 30], 5)
        assert sorted(result, reverse=True) == result  # 降序
        assert set(result) == {10, 20, 30}

    def test_top_three(self):
        result = find_top_n([5, 1, 9, 3, 7, 2, 8], 3)
        assert sorted(result, reverse=True) == result
        assert result == [9, 8, 7]

    def test_duplicates(self):
        result = find_top_n([5, 5, 3, 3, 1, 5], 3)
        assert len(result) == 3
        assert all(x >= 5 for x in result)

    def test_single(self):
        assert find_top_n([42], 3) == [42]

    def test_negative(self):
        result = find_top_n([-5, -1, -3, -10], 2)
        assert result == [-1, -3]
