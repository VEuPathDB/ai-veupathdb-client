### WDK-STEP-001 - A directory named as the enforcing test asserts nothing

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: rules/bad.md
- status: ENFORCED by tests

No separator means no selector, so this used to pass silently.

### WDK-STEP-002 - A directory plus a selector used to throw EISDIR

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: rules/bad.md
- status: PARTIAL by tests::test_nope

Same abort, same hidden violations.
