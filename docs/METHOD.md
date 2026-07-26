# AQA AI Workflows Public Edition method

## Review stages

1. **Intent:** summarize the PR outcome and surface missing acceptance rules.
2. **Mechanics:** map edited paths, symbols where supported, manifests, tests, contracts, configuration, migrations, docs, events, and likely consumers.
3. **Product impact:** infer affected actors, journeys, business rules, data, interfaces, operations, and rollout—with citations and assumptions.
4. **Risk hypotheses:** describe a falsifiable failure mechanism, not a vague quality concern.
5. **Testing direction:** propose prioritized scenarios with objectives, preconditions, steps, expected signals, layers, and evidence.
6. **Challenge:** drop duplicate or unsupported risks, reject unknown evidence IDs, remove prohibited execution claims, and make limitations explicit.
7. **Provenance:** publish exact commits, evidence hashes, provider/model versions, Context Pack receipts, method versions, and staleness.

## Deterministic risk policy

The model supplies five bounded factors and an explanation for each. Python computes the score:

```text
base = 4 × impact + 3 × likelihood + 2 × regression_reach + detectability
evidence_factor = 0.60 + 0.10 × evidence_strength
score = round(base × evidence_factor)
```

Bands:

- Critical: score at least 50 and impact at least 4.
- High: score at least 38.
- Medium: score at least 25.
- Low: everything else.

This policy ranks where human attention may have the most value. It is not a severity system for verified defects and not a release gate.

## Evidence strength

| Value | Meaning |
|---:|---|
| 0 | Speculative; no direct evidence should normally survive validation |
| 1 | Weak lexical or topology clue |
| 2 | Changed-file or contextual evidence supports the hypothesis |
| 3 | Multiple repository sources or a structural match support it |
| 4 | Explicit contract/consumer evidence supports both sides |

## Language and claim rules

Reports may say “risk hypothesis,” “possible impact,” “evidence suggests,” and “requires confirmation.” Reports must not say tests passed/failed, a defect was found, or the release is safe because the application never executes the product.

## Human use

Product should resolve gaps and confirm business impact. QA should edit scenarios using real environment knowledge. Engineering should confirm architecture and downstream consumers. A human owner should decide execution scope and release readiness.
