### WDK-STEP-001 - A directory anchor with no symbol asserts nothing

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: src
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

existsSync is true and there is no symbol, so this used to pass silently.

### WDK-STEP-002 - A directory anchor with a symbol used to throw EISDIR

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: src:StepTree
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

The throw aborted collect and hid every other violation in the bundle.
