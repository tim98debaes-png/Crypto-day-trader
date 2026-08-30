# CI architecture

`Main release CI` is the stable regression gate and must remain fast, deterministic, and independent of experimental research workflows.

Step 1 timing validation and Step 2b historical A-B-C research are intentionally isolated from the release gate. They should be developed and validated on dedicated research branches/workflows and only contribute small deterministic regression tests to Main CI once their contracts are proven stable.

- Main release CI: production/release regression suite.
- Step 1 workflow: isolated timing/execution research validation.
- Step 2b workflow: historical-data benchmark/research validation.
