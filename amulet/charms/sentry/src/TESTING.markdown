
# Adding a function to a module

When adding a function that needs a test, open the modules `tests/test_*.py`
file and write your test. Make sure to increase "attempted" for each test.

This is a basic test:


        try:
            attempted += 1  # do this first of all
            dns.remove_domain("", "")
        except ValueError:
            passed += 1  # we expect to get this error, test passed
        else:
            # no exception was raised!
            lib.log("remove_domain() doesn't raise an exception for"
                " nonexistent domain", error=True)

The function `lib.log()` can be called in three ways:

    - `lib.log("I am Error", error=True)`, an error* (red)

    - `lib.log("hello world")`, an informational message (green)
    - `lib.log("hello world", warning=True)`, a warning (yellow)

Note (*): For convience, each test module will print the number of
error-type log messages after it's done running. This has nothing
to do with the number of attempted and passed tests. I.e. you can
print an error but not fail the test, or vice versa.

        [dns] testing remove_domain()
        [dns] testing remove_domain() with correct arguments
        [dns] testing remove_domain() for nonexistent domain
        [dns] 0 errors logged

The `run()` function will get large fairly quickly: just create
another function for every "suite" of related tests (see the DNS
tests for an example).

# Adding a new module

First, add a new file called `test/test_<modulename>.py` (it's best to copy
an existing file here). Not that the first argument for the run() function
will be the module to be tested. Each of them has a class called `Module()`
which you will probably want to initialize first of all.

Before writing the first test, make sure to call the function by adding it
to the others at near the bottom of `tests.py` like so:

        test_module("dns", results)


# Writing a test

The basic scheme is alwas the same:

 - Increase `attempted`
 - Run some code, make you catch all expected exceptions*
 - If everything is okay, increase `passed`, otherwise don't.

Note (*): If a test raises any exception that travels outside of
the `run()` function, the framework will record it:

        [dns] test raised exception: global name 'apache' is not defined

But **it will not run all the remaining tests properly**. I.e DO rely on this
mechanism to catch bad tests, DO NOT rely on this to fail the test suite.
You should just omit increasing `passed` instead.

If for some reason you **need** a test that fails the entire set of suites
and exits the test, use this pattern instead:

        import sys
        print("i have decided to end all tests here", file=sys.stderr)
        sys.exit(2)


# Running tests

The framework will exit with a return-code 0 of all tests were passed,
2 if a special kind of error happend (for instance, the framework couldn't
load one of the modules you wrote a test for), and 1 if it didn't pass
every single test.


