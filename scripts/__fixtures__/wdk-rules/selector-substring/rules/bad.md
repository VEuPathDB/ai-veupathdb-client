### WDK-STEP-001 - A renamed test must not stay green via substring match

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: rules/bad.md
- status: ENFORCED by tests/test_sample.py::test_step

"test_step" survives inside "test_step_belongs_to_one_strategy".
