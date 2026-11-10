"""
Batch = many scenarios, many runs each, compared side by side; conflicting
outside orders played out as branches (Formal Spec section 13).

Important:
aggregate and conflicts are pure and never import the engine; runner and run
build engines. Nothing below the engine imports this package.
"""
