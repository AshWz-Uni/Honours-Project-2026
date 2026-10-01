"""Ground-truth verification data for the JavaScript problems.

For each problem id:

  fixed_code  reference solution with the intentional bug corrected
  check       body of a JS function that returns ``true`` iff the code behaves
              correctly on inputs that expose the bug (and a few that do not)

The intentionally buggy ``code`` in ``leetcode_eval_js.py`` must FAIL its check
(return false or throw) and ``fixed_code`` must PASS. This is what makes the
"ONE intentional bug" claim testable instead of assumed. These fields are for
the researcher and the test-suite; they are never shown to the tutor.

Run with Node.js on the PATH (see ``backend/tests/test_javascript.py``).
"""

CHECKS = {
    1: {
        "fixed_code": """var twoSum = function(nums, target) {
    for (let i = 0; i < nums.length; i++) {
        for (let j = i + 1; j < nums.length; j++) {
            if (nums[i] + nums[j] === target) {
                return [i, j];
            }
        }
    }
    return [];
};""",
        "check": """
            return JSON.stringify(twoSum([2, 7, 11, 15], 9)) === '[0,1]'
                && JSON.stringify(twoSum([3, 2, 4], 6)) === '[1,2]'
                && JSON.stringify(twoSum([3, 3], 6)) === '[0,1]';
        """,
    },
    2: {
        "fixed_code": """var maxSubArray = function(nums) {
    let current = nums[0];
    let best = nums[0];

    for (let i = 1; i < nums.length; i++) {
        current = Math.max(nums[i], current + nums[i]);
        best = Math.max(best, current);
    }

    return best;
};""",
        "check": """
            return maxSubArray([-3, -2, -5]) === -2
                && maxSubArray([-1]) === -1
                && maxSubArray([7]) === 7
                && maxSubArray([-2, 1, -3, 4, -1, 2, 1, -5, 4]) === 6;
        """,
    },
    3: {
        "fixed_code": """var fizzBuzz = function(n) {
    const result = [];

    for (let i = 1; i <= n; i++) {
        if (i % 15 === 0) {
            result.push("FizzBuzz");
        } else if (i % 3 === 0) {
            result.push("Fizz");
        } else if (i % 5 === 0) {
            result.push("Buzz");
        } else {
            result.push(String(i));
        }
    }

    return result;
};""",
        "check": """
            const expected = ["1","2","Fizz","4","Buzz","Fizz","7","8","Fizz",
                              "Buzz","11","Fizz","13","14","FizzBuzz"];
            return JSON.stringify(fizzBuzz(15)) === JSON.stringify(expected)
                && JSON.stringify(fizzBuzz(1)) === '["1"]'
                && JSON.stringify(fizzBuzz(0)) === '[]';
        """,
    },
    4: {
        "fixed_code": """var climbStairs = function(n) {
    if (n <= 1) {
        return 1;
    }

    let prev = 1;
    let curr = 2;

    for (let i = 2; i < n; i++) {
        [prev, curr] = [curr, prev + curr];
    }

    return curr;
};""",
        "check": """
            return climbStairs(1) === 1
                && climbStairs(2) === 2
                && climbStairs(3) === 3
                && climbStairs(4) === 5
                && climbStairs(5) === 8;
        """,
    },
    5: {
        "fixed_code": """var maxDepth = function(root) {
    if (root === null) {
        return 0;
    }
    return 1 + Math.max(
        maxDepth(root.left),
        maxDepth(root.right)
    );
};""",
        "check": """
            const N = (val, left = null, right = null) => ({ val, left, right });
            return maxDepth(null) === 0
                && maxDepth(N(1)) === 1
                && maxDepth(N(3, N(9), N(20, N(15), N(7)))) === 3;
        """,
    },
    6: {
        "fixed_code": """var reverseList = function(head) {
    let previous = null;
    let current = head;

    while (current) {
        const next = current.next;
        current.next = previous;
        previous = current;
        current = next;
    }

    return previous;
};""",
        "check": """
            const build = (arr) => arr.reduceRight((next, val) => ({ val, next }), null);
            const toArray = (node) => {
                const out = [];
                for (let steps = 0; node && steps < 100; steps++) { out.push(node.val); node = node.next; }
                return out;
            };
            return JSON.stringify(toArray(reverseList(build([1, 2, 3, 4, 5])))) === '[5,4,3,2,1]'
                && JSON.stringify(toArray(reverseList(build([1, 2])))) === '[2,1]'
                && JSON.stringify(toArray(reverseList(build([7])))) === '[7]'
                && reverseList(null) === null;
        """,
    },
    7: {
        "fixed_code": """var containsDuplicate = function(nums) {
    const seen = [];

    for (const num of nums) {
        if (seen.includes(num)) {
            return true;
        }
        seen.push(num);
    }

    return false;
};""",
        "check": """
            return containsDuplicate([1, 2, 1]) === true
                && containsDuplicate([1, 2, 3, 4]) === false
                && containsDuplicate([]) === false
                && containsDuplicate([5]) === false;
        """,
    },
    8: {
        "fixed_code": """var MyQueue = function() {
    this.input = [];
    this.output = [];
};

MyQueue.prototype.push = function(x) {
    this.input.push(x);
};

MyQueue.prototype.refill = function() {
    if (this.output.length === 0) {
        while (this.input.length > 0) {
            this.output.push(this.input.pop());
        }
    }
};

MyQueue.prototype.pop = function() {
    this.refill();
    return this.output.pop();
};

MyQueue.prototype.peek = function() {
    this.refill();
    return this.output[this.output.length - 1];
};

MyQueue.prototype.empty = function() {
    return this.input.length === 0 && this.output.length === 0;
};""",
        "check": """
            const q = new MyQueue();
            q.push(1); q.push(2); q.push(3);
            return q.peek() === 1
                && q.pop() === 1
                && q.pop() === 2
                && q.empty() === false
                && q.pop() === 3
                && q.empty() === true;
        """,
    },
    9: {
        "fixed_code": """var fib = function(n) {
    if (n <= 1) {
        return n;
    }

    let a = 0, b = 1;

    for (let i = 2; i <= n; i++) {
        [a, b] = [b, a + b];
    }

    return b;
};""",
        "check": """
            return fib(0) === 0
                && fib(1) === 1
                && fib(2) === 1
                && fib(3) === 2
                && fib(10) === 55;
        """,
    },
    10: {
        "fixed_code": """var search = function(nums, target) {
    let left = 0;
    let right = nums.length - 1;

    while (left <= right) {
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
        "check": """
            return search([5], 5) === 0
                && search([-1, 0, 3, 5, 9, 12], 9) === 4
                && search([-1, 0, 3, 5, 9, 12], 2) === -1
                && search([], 1) === -1;
        """,
    },
}


# Size of each fix: changed non-blank lines (added + removed, whitespace-trimmed) between the buggy ``code`` and ``fixed_code``. 
# This is a tripwire for the "ONE intentional bug" rule: the executable check only proves the buggy code fails, so an accidental second bug would go unnoticed.
# It would, however, make the real diff larger than the number recorded here.
FIX_DIFF_LINES = {1: 2, 2: 8, 3: 6, 4: 2, 5: 3, 6: 3, 7: 1, 8: 20, 9: 2, 10: 2}
