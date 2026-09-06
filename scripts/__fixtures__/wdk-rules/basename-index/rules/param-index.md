### WDK-PARAMS-1 - A rules file whose name merely ends in index.md is still a rules file

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: rules/param-index.md
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

Only the exact basename index.md is a roster.
