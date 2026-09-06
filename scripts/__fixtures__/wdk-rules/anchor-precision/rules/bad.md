### WDK-STEP-001 - The symbol Step was renamed to WdkStep

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: src/sample.py:Step
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

"Step" survives as a substring of "WdkStep", so the match must be word-bounded.

### WDK-STEP-002 - A nested symbol must not be truncated at the second colon

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: src/sample.py:Foo::bar
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

Splitting on every colon would search for "Foo" alone and pass.
