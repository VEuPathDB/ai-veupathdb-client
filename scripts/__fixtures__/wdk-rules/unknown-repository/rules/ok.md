### WDK-STEP-001 - A step belongs to exactly one strategy

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: some-other-repo: src/steps.py:Step
- status: UNENFORCED
- reason: the fixture names a repository this bundle does not cite.

A step created outside a strategy is an orphan until it is attached.
