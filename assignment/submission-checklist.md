# Submission checklist

- [ ] Solution ID, name, versions, and assigned challenge are explicit.
- [ ] Workflow exports and adapter source are included without credentials.
- [ ] Setup works from a fresh runtime with configurable environment URLs.
- [ ] API accepts the engine's task and per-run environment token.
- [ ] Concurrent attempts do not share candidate state or tokens.
- [ ] Start returns execution ID promptly; status and cancellation work.
- [ ] Terminal submission echoes the original run ID and matches schema v1.0.
- [ ] Final answer distinguishes actions performed from recommendations.
- [ ] No candidate-authored scores or authoritative evidence are submitted.
- [ ] Baseline plus at least three distinct workflow improvements are included.
- [ ] Nine attempts per version use seeds 0/1/2, three repeats each.
- [ ] All attempts and real judge artifacts are retained, including failures.
- [ ] Benchmark package hashes and judge configuration match across comparison.
- [ ] Protected files and the official benchmark lock remain unchanged.
- [ ] Report includes score, duration, success rate, unscored count, and limitations.
- [ ] Dashboard points identify the correct solution names and versions.
- [ ] Claimed improvements refer to recorded evidence, not selected screenshots.

## Experiment report template

| Version | Hypothesis / change | Run IDs | Scored / total | Mean / median score | Mean / median seconds | Execution pass rate | Unscored reasons |
|---|---|---|---|---|---|---|---|
| Baseline | Initial implementation | | /9 | | | | |
| Improvement 1 | | | /9 | | | | |
| Improvement 2 | | | /9 | | | | |
| Improvement 3 | | | /9 | | | | |

Also include the challenge package hashes, judge model/prompt version, seed schedule,
individual run table, known regressions, and what you would change next.
