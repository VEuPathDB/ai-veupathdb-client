### WDK-SITE-001 - A site-model parameter is declared outside WDK

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L1
- anchor: rules/site.md
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

WDK executes the query; it does not define the parameter's grammar.

### WDK-SITES-001 - The plural namespace is not a namespace

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L1
- anchor: rules/site.md
- status: UNENFORCED
- reason: the fixture stands in for a bundle, so no test can hold it.

Only the exact namespace list is admitted.
