<!-- For a PR that implements a CodeAgent-deliberated issue, fill in the contract
     below. For ordinary PRs, you can delete the "CodeAgent PR Contract" section. -->

## Summary

<!-- What does this PR change, and why? -->


## Implements

<!-- The deliberated issue this PR implements, e.g. "Implements: #128".
     Required if you include the CodeAgent PR Contract below. -->
Implements: #


## Testing / Evidence

<!-- How was this verified? -->


## CodeAgent PR Contract

<!-- Generate the skeleton with:
       gh issue view <N> --json body -q .body | python scripts/ca_gate/new_pr_contract.py
     then replace each tests:["TODO"] with the pytest nodeid(s) that prove that AC.
     (A later CI phase reads this and blocks merge until every active AC is proven.)
     If this PR does not implement a deliberated issue, remove this whole section. -->
