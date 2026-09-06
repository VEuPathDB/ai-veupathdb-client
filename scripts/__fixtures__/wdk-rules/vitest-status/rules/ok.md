### WDK-STEP-001 - A vitest node id uses " > " as its separator

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L1
- anchor: rules/ok.md
- status: ENFORCED by tests/sample.test.ts > strategy graph > rejects orphan steps

The selector is the last segment, the path is the first.

### WDK-STEP-002 - A test id with no separator is a bare path

- class: CONTRACT
- upstream: https://raw.githubusercontent.com/VEuPathDB/web-monorepo/6c1f4dc8dd0f0a44ff0f80f27dd97bbd18c56db6/packages/libs/wdk-client/src/Utils/WdkModel.ts
- anchor: rules/ok.md
- status: PARTIAL by tests/sample.test.ts

Existence of the file is all that can be checked.
