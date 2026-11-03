"""Controlled 10-problem LeetCode test set for the Socratic tutoring agent.

The set exists in two languages with identical ids, problems and bugs:

  PROBLEMS       Python      (this file)
  JS_PROBLEMS    JavaScript  (leetcode_eval_js.py)

Use ``get_problems("python" | "javascript")`` or ``PROBLEMS_BY_LANGUAGE``.
``PROBLEMS`` stays the Python list so existing imports keep working.

Each problem has ONE intentional bug. Fields:

  language        "python" or "javascript"
  code            student submission (verbatim from the test plan)
  problem         short paraphrase of the task, passed to the tutor as context
  bug             ground truth for the researcher; NEVER shown to the tutor
  first_response  the student's first message (verbatim from the test plan);
                  it already contains a diagnosis
  fix             scripted follow-up: the student proposes their own fix
  validation      scripted follow-up: the student traces the fix on an input
  reflections     scripted replies to the tutor's three consolidation
                  questions (explain why / edge case / side effects)

`fix`, `validation` and `reflections` are scripted wording written for the
harness so a run needs no human at the keyboard. Edit them freely, and record
any deviations if you drive the conversations by hand instead.
"""

PROBLEMS = [
    {
        "id": 1,
        "name": "Two Sum",
        "code": """class Solution(object):
    def twoSum(self, nums, target):
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    return [i]
        return []""",
        "problem": "Given a list of integers nums and an integer target, return the indices of the two numbers that add up to target. Exactly one such pair exists and the same element cannot be used twice.",
        "bug": "Only one index (i) is returned; the result must contain both indices.",
        "first_response": "Could it be because I only return i when I find the pair? I think I need to return information about both elements.",
        "fix": "So when I find the pair I should return [i, j] instead of just [i].",
        "validation": "I traced [2, 7, 11, 15] with target 9: i=0, j=1 gives 2+7=9, so it now returns [0, 1], which matches.",
        "reflections": [
            "The pair is defined by two positions, so the result has to hold both of them; returning only i lost the second index.",
            "For nums = [3, 3] and target 6 it would return [0, 1], which still works because j starts at i + 1.",
            "It only changes what gets returned, so the loops and the check that already worked are unaffected.",
        ],
        "suggested_validation": "nums = [2, 7, 11, 15], target = 9",
    },
    {
        "id": 2,
        "name": "Maximum Subarray",
        "code": """class Solution(object):
    def maxSubArray(self, nums):
        current = 0
        best = 0

        for num in nums:
            current = max(0, current + num)
            best = max(best, current)

        return best""",
        "problem": "Given an integer array nums, return the largest sum of any non-empty contiguous subarray.",
        "bug": "0 is treated as a valid floor, so an all-negative array returns 0 instead of the largest (least negative) element.",
        "first_response": "The normal examples seem to work, but I think there is something wrong when every number in the array is negative.",
        "fix": "I think I should start best from nums[0] and let current restart at the number itself rather than at 0.",
        "validation": "For [-3, -2, -5] it starts with best = -3, then -2 beats it, then -5 does not, so it returns -2, which is right.",
        "reflections": [
            "Zero is not always a legitimate sum: with all negatives the best non-empty subarray is the least negative element, and my 0 pretended an empty subarray was allowed.",
            "For [7] it returns 7 and for [-1] it returns -1, so single-element arrays work.",
            "The all-positive and mixed cases still work because the running sum only restarts when the number alone is better.",
        ],
        "suggested_validation": "[-3, -2, -5]",
    },
    {
        "id": 3,
        "name": "Fizz Buzz",
        "code": """class Solution(object):
    def fizzBuzz(self, n):
        result = []

        for i in range(1, n + 1):
            if i % 3 == 0:
                result.append("Fizz")
            elif i % 5 == 0:
                result.append("Buzz")
            elif i % 15 == 0:
                result.append("FizzBuzz")
            else:
                result.append(str(i))

        return result""",
        "problem": "Return a list of strings for 1..n: 'FizzBuzz' if divisible by both 3 and 5, 'Fizz' if divisible by 3, 'Buzz' if divisible by 5, otherwise the number as a string.",
        "bug": "The i % 15 branch is unreachable because multiples of 15 are caught by the i % 3 branch first.",
        "first_response": "I think the problem might happen for numbers that are divisible by both 3 and 5, because one of the earlier conditions catches them first.",
        "fix": "I would check divisibility by 15 first, before the checks for 3 and 5.",
        "validation": "With n = 15, i = 15 hits the 15 check first and appends FizzBuzz, while 3 still gives Fizz and 5 gives Buzz.",
        "reflections": [
            "The conditions are checked in order and the first true one wins, so the most specific case has to come before the general ones.",
            "For n = 1 the list is ['1'], and for n = 0 the loop does not run so it returns [].",
            "Only the order changed, so numbers divisible by just 3 or just 5 still reach the same branches as before.",
        ],
        "suggested_validation": "n = 15",
    },
    {
        "id": 4,
        "name": "Climbing Stairs",
        "code": """class Solution(object):
    def climbStairs(self, n):
        if n <= 1:
            return 1

        prev = 1
        curr = 2

        for i in range(2, n):
            prev, curr = curr, prev + curr

        return prev""",
        "problem": "You climb a staircase of n steps, taking 1 or 2 steps at a time. Return the number of distinct ways to reach the top.",
        "bug": "Off-by-one between loop and return: for n = 3 it returns 2 instead of 3 (should return curr).",
        "first_response": "I think my Fibonacci-style update is shifted by one step because the result for 3 stairs does not match what I expect.",
        "fix": "I think I should return curr instead of prev, since curr holds the answer for the current n.",
        "validation": "For n = 3 the loop runs once, prev and curr become 2 and 3, and returning curr gives 3. For n = 2 it gives 2 and for n = 4 it gives 5.",
        "reflections": [
            "After the loop curr holds the count for n and prev holds the count for n - 1, so I was returning the wrong one.",
            "n = 1 hits the early return of 1, and n = 2 skips the loop and returns curr = 2, which is right.",
            "The loop update is untouched, so the sequence of values is the same; only the final return changed.",
        ],
        "suggested_validation": "n = 2, 3, 4",
    },
    {
        "id": 5,
        "name": "Maximum Depth of Binary Tree",
        "code": """class Solution(object):
    def maxDepth(self, root):
        return 1 + max(
            self.maxDepth(root.left),
            self.maxDepth(root.right)
        )""",
        "problem": "Given the root of a binary tree, return its maximum depth: the number of nodes on the longest path from the root down to a leaf. An empty tree has depth 0.",
        "bug": "No base case for an empty node (None); root.left is accessed on None.",
        "first_response": "The recursion reaches an empty child, but my function still tries to access its children. I think I'm missing a condition for that case.",
        "fix": "I think I should return 0 when root is None before touching root.left and root.right.",
        "validation": "For a tree with only a root, both children are None so each recursive call returns 0 and the result is 1 + max(0, 0) = 1.",
        "reflections": [
            "Without it the recursion goes past the leaves and tries to read .left on None; the base case is where the recursion stops.",
            "An empty tree (root is None) returns 0 immediately, which matches the requirement.",
            "Non-empty trees behave as before since the new check only triggers on None, and each real node still adds 1 to the deeper side.",
        ],
        "suggested_validation": "a tree containing only a root node",
    },
    {
        "id": 6,
        "name": "Reverse Linked List",
        "code": """class Solution(object):
    def reverseList(self, head):
        previous = None
        current = head

        while current:
            current.next = previous
            previous = current
            current = current.next

        return previous""",
        "problem": "Given the head of a singly linked list, reverse the list and return the new head.",
        "bug": "current.next is overwritten before the original next node is saved, so the traversal loses the rest of the list.",
        "first_response": "I think I am losing the next node when I change current.next. The pointer I use to continue might no longer point to the original next node.",
        "fix": "I would save current.next in a temporary variable before changing it, and then move forward using the saved one.",
        "validation": "With 1 -> 2 -> None: save 2, point 1 to None, previous = 1, current = 2; then save None, point 2 to 1, previous = 2, current = None, so it returns 2 -> 1 -> None.",
        "reflections": [
            "Setting current.next overwrites the only link to the rest of the list, so it has to be remembered first.",
            "An empty list skips the loop and returns None, and a single node returns itself with next = None.",
            "The pointer reversal is the same; only the order of statements and one saved reference changed, so nodes still end up linked backwards.",
        ],
        "suggested_validation": "1 -> 2 -> None",
    },
    {
        "id": 7,
        "name": "Contains Duplicate",
        "code": """class Solution(object):
    def containsDuplicate(self, nums):
        seen = []

        for num in nums:
            if num in seen:
                return True

        return False""",
        "problem": "Given a list of integers nums, return True if any value appears at least twice, otherwise return False.",
        "bug": "Values are never added to seen, so duplicates can never be detected.",
        "first_response": "I'm checking whether a value is already in seen, but I never seem to store the values I've visited. Could that be why duplicates are missed?",
        "fix": "I should append num to seen at the end of each loop iteration when it is not already there.",
        "validation": "For [1, 2, 1]: seen is [] then [1] then [1, 2], and when I reach the second 1 it is in seen so it returns True.",
        "reflections": [
            "The membership check only works if seen holds the values already visited, so each value has to be recorded after it is checked.",
            "For [] or [5] the loop finds no repeat and returns False, which is right.",
            "Only one line was added; the early return True and the final return False behave the same.",
        ],
        "suggested_validation": "nums = [1, 2, 1], trace seen after every iteration",
    },
    {
        "id": 8,
        "name": "Implement Queue Using Stacks",
        "code": """class MyQueue(object):

    def __init__(self):
        self.stack = []

    def push(self, x):
        self.stack.append(x)

    def pop(self):
        return self.stack.pop()

    def peek(self):
        return self.stack[-1]

    def empty(self):
        return len(self.stack) == 0""",
        "problem": "Implement a first-in-first-out queue (push, pop, peek, empty) using only stack operations: push to top, pop from top, peek at top, size and is-empty.",
        "bug": "A single stack gives LIFO behaviour; pop returns the newest item where a queue must return the oldest.",
        "first_response": "My push works, but pop gives me the most recently added item. I think the way I'm using the stack doesn't match the queue's ordering requirement.",
        "fix": "I think I need a second stack so that when I pop or peek, I can move the items over and reverse their order.",
        "validation": "After push 1, 2, 3 and moving them into the second stack, the top is 1, so peek() gives 1, and pop() gives 1 then 2, which is FIFO.",
        "reflections": [
            "Moving items from one stack to another reverses their order, so the oldest item ends up on top.",
            "Popping an empty queue should fail like an empty stack does, and empty() must be True only when both stacks are empty.",
            "push can stay the same, but empty() has to check both stacks, and I should only refill the second stack when it is empty so the order is not mixed up.",
        ],
        "suggested_validation": "push(1), push(2), push(3), peek(), pop(), pop()",
    },
    {
        "id": 9,
        "name": "Fibonacci Number",
        "code": """class Solution(object):
    def fib(self, n):
        if n <= 1:
            return 1

        a, b = 0, 1

        for i in range(2, n + 1):
            a, b = b, a + b

        return b""",
        "problem": "Return F(n), where F(0) = 0, F(1) = 1 and F(n) = F(n-1) + F(n-2).",
        "bug": "The base case returns 1 for n = 0; F(0) must be 0.",
        "first_response": "I think my base case treats 0 and 1 the same, but Fibonacci has different values for those two inputs.",
        "fix": "I think the early return should give n itself for n <= 1, so 0 returns 0 and 1 returns 1.",
        "validation": "fib(0) returns 0 and fib(1) returns 1; for fib(2) the loop runs once giving 1, and fib(3) gives 2, which are all right.",
        "reflections": [
            "F(0) and F(1) are different starting values, so one shared return cannot be right for both.",
            "fib(0) was the edge case I had wrong; fib(1) and larger n were already fine.",
            "The loop only runs for n >= 2 so it is not affected; only the two smallest inputs change.",
        ],
        "suggested_validation": "fib(0), fib(1), fib(2), fib(3)",
    },
    {
        "id": 10,
        "name": "Binary Search",
        "code": """class Solution(object):
    def search(self, nums, target):
        left = 0
        right = len(nums) - 1

        while left < right:
            mid = (left + right) // 2

            if nums[mid] == target:
                return mid
            elif nums[mid] < target:
                left = mid + 1
            else:
                right = mid - 1

        return -1""",
        "problem": "Given a sorted list nums and a target, return the index of target in nums, or -1 if it is not present.",
        "bug": "The loop stops when left == right without checking that last candidate; nums=[5], target=5 returns -1.",
        "first_response": "I think the loop stops when left and right become the same index, even though that index could still contain the target.",
        "fix": "I would let the loop keep running while left is less than or equal to right so the last remaining index is also checked.",
        "validation": "With [5] and target 5, left and right are both 0 so the loop now runs, mid is 0, nums[0] equals 5, and it returns 0.",
        "reflections": [
            "left and right are both inclusive bounds, so when they are equal there is still one candidate left to check.",
            "For an empty list right is -1, so the loop condition is False and it returns -1 immediately.",
            "The updates left = mid + 1 and right = mid - 1 still shrink the range each time, so it cannot loop forever.",
        ],
        "suggested_validation": "nums = [5], target = 5",
    },
]


for _problem in PROBLEMS:
    _problem.setdefault("language", "python")

from dataset.leetcode_eval_js import JS_PROBLEMS  # noqa: E402

PROBLEMS_BY_LANGUAGE = {
    "python": PROBLEMS,
    "javascript": JS_PROBLEMS,
}


def get_problems(language: str = "python") -> list[dict]:
    """Return the 10-problem set for ``language`` ("python" or "javascript")."""
    try:
        return PROBLEMS_BY_LANGUAGE[language]
    except KeyError:
        raise ValueError(
            f"Unknown language {language!r}; expected one of {sorted(PROBLEMS_BY_LANGUAGE)}"
        ) from None
