"""
Synthetic dataset of 10 student-level Python functions, each containing
exactly one deliberate bug or quality issue. Used as the evaluation corpus
for the Code Llama tutoring agent experiment.

Each entry in SAMPLES is a dict with:
  - id            : integer 1–10
  - concept       : human-readable label of the programming concept
  - buggy_code    : the code string submitted to the agent
  - bug_type      : short category of the fault
  - bug_keywords  : list of terms that MUST appear in the agent's response
                    for Issue Detection Rate (IDR) to score 1
  - ground_truth  : plain-English description of the bug (for QRS scoring)
"""

SAMPLES = [

    # ── 1 ─────────────────────────────────────────────────────────────────
    {
        "id": 1,
        "concept": "List Summation (sum_list)",
        "bug_type": "Off-by-one error",
        "buggy_code": """\
def sum_list(lst):
    total = 0
    for i in range(1, len(lst)):   # BUG: should start at 0, skips first element
        total += lst[i]
    return total
""",
        "bug_keywords": ["range", "index", "0", "first", "element", "start"],
        "ground_truth": (
            "The loop starts at index 1, so the element at index 0 is never "
            "added to total. The range should be range(0, len(lst)) or simply "
            "range(len(lst))."
        ),
    },

    # ── 2 ─────────────────────────────────────────────────────────────────
    {
        "id": 2,
        "concept": "Bubble Sort",
        "bug_type": "Inefficient inner loop (missing optimisation)",
        "buggy_code": """\
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(n - 1):     # BUG: should be range(n - 1 - i) to avoid re-checking sorted tail
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
""",
        "bug_keywords": ["inner", "loop", "range", "sorted", "pass", "i", "n - 1 - i", "shrink"],
        "ground_truth": (
            "The inner loop always runs from 0 to n-2, even though the largest "
            "element is already in its correct position after each outer pass. "
            "It should be range(n - 1 - i) to avoid unnecessary comparisons."
        ),
    },

    # ── 3 ─────────────────────────────────────────────────────────────────
    {
        "id": 3,
        "concept": "Palindrome Check",
        "bug_type": "Assignment instead of comparison operator",
        "buggy_code": """\
def is_palindrome(s):
    s = s.lower()
    reversed_s = s[::-1]
    if s = reversed_s:             # BUG: SyntaxError — should be == not =
        return True
    return False
""",
        "bug_keywords": ["=", "==", "assignment", "comparison", "operator", "syntax"],
        "ground_truth": (
            "The condition uses a single = (assignment operator) instead of "
            "== (equality comparison), which is a SyntaxError in Python."
        ),
    },

    # ── 4 ─────────────────────────────────────────────────────────────────
    {
        "id": 4,
        "concept": "Recursive Factorial",
        "bug_type": "Missing base case (infinite recursion)",
        "buggy_code": """\
def factorial(n):
    # BUG: no base case — will recurse forever and raise RecursionError
    return n * factorial(n - 1)
""",
        "bug_keywords": ["base case", "recursion", "base", "0", "1", "stop", "terminate", "infinite"],
        "ground_truth": (
            "There is no base case to stop the recursion. When n reaches 0 or 1 "
            "the function should return 1 instead of calling itself again."
        ),
    },

    # ── 5 ─────────────────────────────────────────────────────────────────
    {
        "id": 5,
        "concept": "Linear Search",
        "bug_type": "Missing return value for not-found case",
        "buggy_code": """\
def linear_search(lst, target):
    for i in range(len(lst)):
        if lst[i] == target:
            return i
    # BUG: implicit return None when target is not found — caller cannot distinguish
    #      'not found' from a valid result of None without extra checks
""",
        "bug_keywords": ["return", "not found", "none", "-1", "missing", "else", "explicit"],
        "ground_truth": (
            "When the target is not in the list the function returns None "
            "implicitly. A convention like returning -1 (or raising a ValueError) "
            "should be used so callers can detect the not-found case unambiguously."
        ),
    },

    # ── 6 ─────────────────────────────────────────────────────────────────
    {
        "id": 6,
        "concept": "Vowel Counter",
        "bug_type": "Case-sensitivity bug",
        "buggy_code": """\
def count_vowels(s):
    count = 0
    vowels = "aeiou"               # BUG: only lowercase — uppercase vowels missed
    for ch in s:
        if ch in vowels:
            count += 1
    return count
""",
        "bug_keywords": ["uppercase", "lower", "case", "A", "E", "I", "O", "U", "upper"],
        "ground_truth": (
            "The vowels string only contains lowercase letters. Characters like "
            "'A', 'E', 'I', 'O', 'U' will not be counted. The input string (or "
            "the vowels set) should be converted to a consistent case first."
        ),
    },

    # ── 7 ─────────────────────────────────────────────────────────────────
    {
        "id": 7,
        "concept": "Celsius to Fahrenheit Conversion",
        "bug_type": "Inverted formula",
        "buggy_code": """\
def celsius_to_fahrenheit(c):
    return (c - 32) * 5 / 9        # BUG: this is the Fahrenheit→Celsius formula
                                   #      should be (c * 9/5) + 32
""",
        "bug_keywords": ["formula", "32", "9", "5", "multiply", "add", "subtract", "fahrenheit", "celsius"],
        "ground_truth": (
            "The formula applied is (c - 32) * 5/9, which converts Fahrenheit "
            "to Celsius, not the other way around. The correct formula is "
            "(c * 9/5) + 32."
        ),
    },

    # ── 8 ─────────────────────────────────────────────────────────────────
    {
        "id": 8,
        "concept": "Flatten Nested List",
        "bug_type": "append vs extend confusion",
        "buggy_code": """\
def flatten_list(lst):
    result = []
    for sublist in lst:
        result.append(sublist)     # BUG: appends the sublist as a single element
                                   #      should be result.extend(sublist)
    return result
""",
        "bug_keywords": ["append", "extend", "sublist", "nested", "element", "flat"],
        "ground_truth": (
            "result.append(sublist) adds the entire sublist as a single element, "
            "so the output is still a list of lists. result.extend(sublist) should "
            "be used to add each element of the sublist individually."
        ),
    },

    # ── 9 ─────────────────────────────────────────────────────────────────
    {
        "id": 9,
        "concept": "Binary Search",
        "bug_type": "Operator precedence error in midpoint calculation",
        "buggy_code": """\
def binary_search(lst, target):
    low, high = 0, len(lst) - 1
    while low <= high:
        mid = low + high // 2      # BUG: operator precedence — evaluates as low + (high//2)
                                   #      should be (low + high) // 2
        if lst[mid] == target:
            return mid
        elif lst[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
""",
        "bug_keywords": ["precedence", "parenthes", "mid", "low + high", "//", "operator", "midpoint"],
        "ground_truth": (
            "Due to operator precedence, low + high // 2 is evaluated as "
            "low + (high // 2), not (low + high) // 2. This produces an incorrect "
            "midpoint and will cause the search to behave wrongly or loop infinitely."
        ),
    },

    # ── 10 ────────────────────────────────────────────────────────────────
    {
        "id": 10,
        "concept": "Remove Duplicates from List",
        "bug_type": "Mutating a list while iterating over it",
        "buggy_code": """\
def remove_duplicates(lst):
    seen = []
    for item in lst:               # BUG: modifying lst while iterating — skips elements
        if item in seen:
            lst.remove(item)
        else:
            seen.append(item)
    return lst
""",
        "bug_keywords": ["modify", "mutate", "iterate", "remove", "while", "loop", "skip", "copy"],
        "ground_truth": (
            "Calling lst.remove(item) while iterating over lst causes the iterator "
            "to skip elements because the list is being modified in place. The loop "
            "should iterate over a copy of the list, or build a new result list."
        ),
    },
]
