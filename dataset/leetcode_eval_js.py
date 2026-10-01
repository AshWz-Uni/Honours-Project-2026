"""JavaScript equivalents of the 10-problem LeetCode test set.

Same problems, same ids, same ONE intentional bug per problem as the Python set
in ``leetcode_eval.py``, so results for the two languages are directly
comparable. The code follows LeetCode's JavaScript templates
(``var twoSum = function(nums, target) {...}``; ``MyQueue.prototype.push``).

The schema is identical to the Python set (``code``, ``problem``, ``bug``,
``first_response``, ``fix``, ``validation``, ``reflections``,
``suggested_validation``) plus ``"language": "javascript"``. Wording is kept
close to the Python set on purpose; only language-specific terms change
(array/null/``true``/``false``, ``push``, ``Math.floor``).

``dataset/leetcode_eval_js_checks.py`` holds a reference fix and an executable
check for each problem so the ground-truth bugs can be verified with Node.
"""

JS_PROBLEMS = [
    {
        "id": 1,
        "language": "javascript",
        "name": "Two Sum",
        "code": """var twoSum = function(nums, target) {
    for (let i = 0; i < nums.length; i++) {
        for (let j = i + 1; j < nums.length; j++) {
            if (nums[i] + nums[j] === target) {
                return [i];
            }
        }
    }
    return [];
};""",
        "problem": "Given an array of integers nums and an integer target, return the indices of the two numbers that add up to target. Exactly one such pair exists and the same element cannot be used twice.",
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
        "language": "javascript",
        "name": "Maximum Subarray",
        "code": """var maxSubArray = function(nums) {
    let current = 0;
    let best = 0;

    for (const num of nums) {
        current = Math.max(0, current + num);
        best = Math.max(best, current);
    }

    return best;
};""",
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
        "language": "javascript",
        "name": "Fizz Buzz",
        "code": """var fizzBuzz = function(n) {
    const result = [];

    for (let i = 1; i <= n; i++) {
        if (i % 3 === 0) {
            result.push("Fizz");
        } else if (i % 5 === 0) {
            result.push("Buzz");
        } else if (i % 15 === 0) {
            result.push("FizzBuzz");
        } else {
            result.push(String(i));
        }
    }

    return result;
};""",
        "problem": "Return an array of strings for 1..n: 'FizzBuzz' if divisible by both 3 and 5, 'Fizz' if divisible by 3, 'Buzz' if divisible by 5, otherwise the number as a string.",
        "bug": "The i % 15 branch is unreachable because multiples of 15 are caught by the i % 3 branch first.",
        "first_response": "I think the problem might happen for numbers that are divisible by both 3 and 5, because one of the earlier conditions catches them first.",
        "fix": "I would check divisibility by 15 first, before the checks for 3 and 5.",
        "validation": "With n = 15, i = 15 hits the 15 check first and pushes FizzBuzz, while 3 still gives Fizz and 5 gives Buzz.",
        "reflections": [
            "The conditions are checked in order and the first true one wins, so the most specific case has to come before the general ones.",
            "For n = 1 the array is ['1'], and for n = 0 the loop does not run so it returns [].",
            "Only the order changed, so numbers divisible by just 3 or just 5 still reach the same branches as before.",
        ],
        "suggested_validation": "n = 15",
    },
    {
        "id": 4,
        "language": "javascript",
        "name": "Climbing Stairs",
        "code": """var climbStairs = function(n) {
    if (n <= 1) {
        return 1;
    }

    let prev = 1;
    let curr = 2;

    for (let i = 2; i < n; i++) {
        [prev, curr] = [curr, prev + curr];
    }

    return prev;
};""",
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
        "language": "javascript",
        "name": "Maximum Depth of Binary Tree",
        "code": """var maxDepth = function(root) {
    return 1 + Math.max(
        maxDepth(root.left),
        maxDepth(root.right)
    );
};""",
        "problem": "Given the root of a binary tree (each node has val, left and right; a missing child is null), return its maximum depth: the number of nodes on the longest path from the root down to a leaf. An empty tree has depth 0.",
        "bug": "No base case for an empty node (null); root.left is accessed on null, which throws a TypeError.",
        "first_response": "The recursion reaches an empty child, but my function still tries to access its children. I think I'm missing a condition for that case.",
        "fix": "I think I should return 0 when root is null before touching root.left and root.right.",
        "validation": "For a tree with only a root, both children are null so each recursive call returns 0 and the result is 1 + Math.max(0, 0) = 1.",
        "reflections": [
            "Without it the recursion goes past the leaves and tries to read .left on null; the base case is where the recursion stops.",
            "An empty tree (root is null) returns 0 immediately, which matches the requirement.",
            "Non-empty trees behave as before since the new check only triggers on null, and each real node still adds 1 to the deeper side.",
        ],
        "suggested_validation": "a tree containing only a root node",
    },
    {
        "id": 6,
        "language": "javascript",
        "name": "Reverse Linked List",
        "code": """var reverseList = function(head) {
    let previous = null;
    let current = head;

    while (current) {
        current.next = previous;
        previous = current;
        current = current.next;
    }

    return previous;
};""",
        "problem": "Given the head of a singly linked list (each node has val and next; the end of the list is null), reverse the list and return the new head.",
        "bug": "current.next is overwritten before the original next node is saved, so the traversal loses the rest of the list.",
        "first_response": "I think I am losing the next node when I change current.next. The pointer I use to continue might no longer point to the original next node.",
        "fix": "I would save current.next in a temporary variable before changing it, and then move forward using the saved one.",
        "validation": "With 1 -> 2 -> null: save 2, point 1 to null, previous = 1, current = 2; then save null, point 2 to 1, previous = 2, current = null, so it returns 2 -> 1 -> null.",
        "reflections": [
            "Setting current.next overwrites the only link to the rest of the list, so it has to be remembered first.",
            "An empty list skips the loop and returns null, and a single node returns itself with next = null.",
            "The pointer reversal is the same; only the order of statements and one saved reference changed, so nodes still end up linked backwards.",
        ],
        "suggested_validation": "1 -> 2 -> null",
    },
    {
        "id": 7,
        "language": "javascript",
        "name": "Contains Duplicate",
        "code": """var containsDuplicate = function(nums) {
    const seen = [];

    for (const num of nums) {
        if (seen.includes(num)) {
            return true;
        }
    }

    return false;
};""",
        "problem": "Given an array of integers nums, return true if any value appears at least twice, otherwise return false.",
        "bug": "Values are never added to seen, so duplicates can never be detected.",
        "first_response": "I'm checking whether a value is already in seen, but I never seem to store the values I've visited. Could that be why duplicates are missed?",
        "fix": "I should push num onto seen at the end of each loop iteration when it is not already there.",
        "validation": "For [1, 2, 1]: seen is [] then [1] then [1, 2], and when I reach the second 1 it is in seen so it returns true.",
        "reflections": [
            "The membership check only works if seen holds the values already visited, so each value has to be recorded after it is checked.",
            "For [] or [5] the loop finds no repeat and returns false, which is right.",
            "Only one line was added; the early return true and the final return false behave the same.",
        ],
        "suggested_validation": "nums = [1, 2, 1], trace seen after every iteration",
    },
    {
        "id": 8,
        "language": "javascript",
        "name": "Implement Queue Using Stacks",
        "code": """var MyQueue = function() {
    this.stack = [];
};

MyQueue.prototype.push = function(x) {
    this.stack.push(x);
};

MyQueue.prototype.pop = function() {
    return this.stack.pop();
};

MyQueue.prototype.peek = function() {
    return this.stack[this.stack.length - 1];
};

MyQueue.prototype.empty = function() {
    return this.stack.length === 0;
};""",
        "problem": "Implement a first-in-first-out queue (push, pop, peek, empty) using only stack operations: push to top, pop from top, peek at top, size and is-empty.",
        "bug": "A single stack gives LIFO behaviour; pop returns the newest item where a queue must return the oldest.",
        "first_response": "My push works, but pop gives me the most recently added item. I think the way I'm using the stack doesn't match the queue's ordering requirement.",
        "fix": "I think I need a second stack so that when I pop or peek, I can move the items over and reverse their order.",
        "validation": "After push 1, 2, 3 and moving them into the second stack, the top is 1, so peek() gives 1, and pop() gives 1 then 2, which is FIFO.",
        "reflections": [
            "Moving items from one stack to another reverses their order, so the oldest item ends up on top.",
            "Popping an empty queue should fail like an empty stack does, and empty() must be true only when both stacks are empty.",
            "push can stay the same, but empty() has to check both stacks, and I should only refill the second stack when it is empty so the order is not mixed up.",
        ],
        "suggested_validation": "push(1), push(2), push(3), peek(), pop(), pop()",
    },
    {
        "id": 9,
        "language": "javascript",
        "name": "Fibonacci Number",
        "code": """var fib = function(n) {
    if (n <= 1) {
        return 1;
    }

    let a = 0, b = 1;

    for (let i = 2; i <= n; i++) {
        [a, b] = [b, a + b];
    }

    return b;
};""",
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
        "language": "javascript",
        "name": "Binary Search",
        "code": """var search = function(nums, target) {
    let left = 0;
    let right = nums.length - 1;

    while (left < right) {
        const mid = Math.floor((left + right) / 2);

        if (nums[mid] === target) {
            return mid;
        } else if (nums[mid] < target) {
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }

    return -1;
};""",
        "problem": "Given a sorted array nums and a target, return the index of target in nums, or -1 if it is not present.",
        "bug": "The loop stops when left == right without checking that last candidate; nums=[5], target=5 returns -1.",
        "first_response": "I think the loop stops when left and right become the same index, even though that index could still contain the target.",
        "fix": "I would let the loop keep running while left is less than or equal to right so the last remaining index is also checked.",
        "validation": "With [5] and target 5, left and right are both 0 so the loop now runs, mid is 0, nums[0] equals 5, and it returns 0.",
        "reflections": [
            "left and right are both inclusive bounds, so when they are equal there is still one candidate left to check.",
            "For an empty array right is -1, so the loop condition is false and it returns -1 immediately.",
            "The updates left = mid + 1 and right = mid - 1 still shrink the range each time, so it cannot loop forever.",
        ],
        "suggested_validation": "nums = [5], target = 5",
    },
]
