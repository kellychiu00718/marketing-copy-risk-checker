# Evaluation protocol and results

English summary of `docs/eval_protocol.md` (written in Korean). Evaluated 2026-10-06 (KST).

## Goal
Compare three ways of deciding "a person should check this copy": the rules layer alone, the LLM alone, and the cascade (rules first, LLM only when the rules are not highly confident).

## Data
- 48 synthetic sentences. They are not real ads or real events.
- Development set, 24 cases (`tests/cases_dev.yaml`): used while fixing rules and prompts.
- Blind test set, 24 cases (`tests/cases_test.yaml`): written and locked before the rules were changed, evaluated once at the end.
  - SHA-256 at lock time: `46fd0902cc60df3958ff87d85f42cb9790087f9947bf3a2621ce5302481b1607`. If the file hashes to something else, it was edited after the lock (`shasum -a 256 tests/cases_test.yaml`).

## Rules of the evaluation
1. Rules and prompts are changed using development results only.
2. The test set is run once at the end. The numbers are reported as they are, even if they look bad. If I change a rule after reporting, those cases move to the development set and a new test set is written.
3. The LLM is not deterministic, so the test set runs twice and the agreement between runs is reported.
4. Confidence intervals are Wilson 95%. McNemar uses the exact test.

## Known limits (read the results with these)
- One person wrote the labels and the rules. The rules inevitably resemble my labeling taste, so the results lean optimistic. The best fix is two independent reviewers.
- The test set contains some false-positive patterns I already knew about (idioms), so it is not fully blind.
- 24 cases is small. The intervals are wide, so the results show direction, not a winner.
- Cases marked `policy: true` (mentioning a national holiday, text containing instructions) may be labeled differently under another team's policy.
- The cases do not represent the distribution of real marketing copy. Re-evaluate on real usage before any deployment.

## Results

### Development set (24 cases): reference only, because rules and prompts were tuned on it
| Mode | Precision | Recall | Note |
|---|---|---|---|
| Rules only | 1.00 | 0.67 | Missed 4 cases that need meaning |
| LLM only | 1.00 | 1.00 | After one prompt change (one false positive before) |
| Cascade | 1.00 | 1.00 | LLM calls 24 to 19 |

### Blind test set (24 cases, rules unchanged, two runs): the only table to quote
| Mode | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Same verdict on both runs | LLM calls |
|---|---|---|---|---|---|---|---|---|
| Rules only | 10 | 0 | 4 | 10 | 1.00 [0.72–1.00] | 0.71 [0.45–0.88] | 100% | 0 |
| LLM only | 11 | 0 | 3 | 10 | 1.00 [0.74–1.00] | 0.79 [0.52–0.92] | 88% | 24 |
| Cascade | 14 | 0 | 0 | 10 | 1.00 [0.78–1.00] | 1.00 [0.78–1.00] | 100% | 18 |

McNemar exact test: rules vs cascade p = 0.125, LLM vs cascade p = 0.250, rules vs LLM p = 1.000. **No pair differs significantly.**

### How to read this
**Facts**
- The 4 cases the rules missed (t13 to t16) all need a judgment on meaning (stereotype, discrimination, a health claim).
- The 3 cases the LLM alone missed (t04 June 6 memorial day, t06 a December 29 memorial day, t11 an election polling place) all need calendar or election knowledge. The LLM-only mode does not use the rules layer's calendar.
- The two modes missed different cases. On these 24 cases the cascade, which combines them, missed none.
- The LLM-only mode gave a different verdict on 3 of 24 inputs (12%) when the same input was run twice. Rules and cascade never did.

**Interpretation (inference)**
- The benefit of the cascade looks like the two layers making different kinds of mistakes, more than the saving in LLM calls (24 to 18).
- The sample is small and the intervals are wide (cascade recall lower bound 0.78), so I cannot claim it is statistically better.
- Because one person wrote the labels and the rules, there is optimism bias. Re-evaluate with two independent labelers (report Cohen's kappa) and a sample of real marketing copy.

## Next evaluation
1. Add at least one independent labeler, then report label agreement (kappa) and re-label the policy-dependent cases.
2. The test set is used up, so write and lock a new blind set of 24 or more cases.
3. Re-measure precision on real usage records, including false-positive reports.
