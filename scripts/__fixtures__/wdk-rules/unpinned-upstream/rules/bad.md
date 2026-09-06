### WDK-STEP-001 - A step belongs to exactly one strategy

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/main/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: rules/bad.md
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

A step created outside a strategy is an orphan until it is attached.
