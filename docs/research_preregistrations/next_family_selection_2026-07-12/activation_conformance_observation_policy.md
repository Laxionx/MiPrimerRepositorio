# Activation, implementation conformance, and observation policy

## Prospective activation boundary

Merging PR #28 alone does not start prospective validation. Prospective evidence may
begin only when all seven requirements below are complete and recorded:

1. this preregistration is merged;
2. the implementation commit is reviewed and frozen;
3. the finalized feature-provenance artifact is reviewed and frozen;
4. all implementation-conformance tests pass;
5. the exact execution configuration is frozen;
6. a machine-readable activation record is committed; and
7. a non-backdated UTC activation timestamp is recorded.

The activation timestamp must be at or after the activation-record commit timestamp;
it cannot be backdated. Data before it is not prospective confirmation data. Data
collected while implementation semantics or configuration remain changeable is
contaminated. No prospective activation timestamp exists for this draft package.

The future activation record must contain `family_id`, preregistration commit,
implementation commit, finalized provenance-artifact SHA-256, execution-configuration
SHA-256, conformance-test result reference, activation-record commit, activation UTC
timestamp, complete symbol/timeframe universe, and software/schema versions.

## Mandatory implementation conformance

The later implementation PR must show deterministic synthetic input fixtures and exact
expected event streams. It must include warm-up boundary, threshold equality,
immediately-below/above threshold, regime transition, same-bar confirmation, reset,
re-arming, persistence, no-cooldown, missing-value, gap, duplicate-event,
overlapping-event, canonical-event-ID, symbol/timeframe-isolation, provenance-contract,
and strict-eligibility tests.

It must report the preregistration-manifest SHA-256, implementation commit, extracted
implementation configuration, machine-readable semantic-diff result against the
manifest, and conformance-test results. A material semantic difference blocks
real-data execution until a newly versioned preregistration is reviewed and merged.

## First-real-data observation boundary

Before displaying, summarizing, or inspecting family performance, execution must
create and preserve an immutable observation record containing the preregistration
version, implementation commit, activation record, input-artifact hashes, execution
configuration hash, command, start UTC timestamp, output directory, and expected
report schemas. The record is the irreversible observation boundary.

After performance is observed, detector semantics, thresholds, lookbacks, features,
universe, timeframes, periods, gates, costs, outcome geometry, support requirements,
and scorecard may not change under the same confirmatory version. Every run and its
artifacts remain preserved and linked; failed or unfavorable evidence must not be
overwritten, deleted, or silently regenerated.

## Post-observation defect policy

A discovered defect must preserve the original run and artifacts, record the defect
and minimal reproduction, identify every affected run, and classify whether it affects
event generation, features, costs, outcomes, or reporting. A fix requires a new
implementation commit and new execution/version ID; it never silently replaces prior
results and must state whether prior development conclusions are invalid. A new
prospective boundary is mandatory when the fix could be influenced by observed results
or changes confirmatory semantics. A corrected rerun may repair invalid evidence but
cannot claim the original observation never occurred.
