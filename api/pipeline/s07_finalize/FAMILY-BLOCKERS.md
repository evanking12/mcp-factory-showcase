# S-07 Family Blockers

S-07 owns final operator-facing closure over the evidence already produced. It
should classify blockers around closure quality, final artifacts, and
unsupported claims.

## handles

| Blocker family | Stage stance |
| --- | --- |
| final status needs harmonization | Harmonize final findings where evidence supports it. |
| behavioral summary can be emitted | Emit `behavioral_spec.py` when possible. |
| final vocab/description needs refresh | Update final vocabulary and description when supported. |
| optional description model call stalls | Use deterministic description by default; if model synthesis is explicitly enabled, bound it, record span failure, and continue final close. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| unresolved clarification remains | Surface open status rather than hiding it. |
| verification incomplete | Preserve verified/inferred distinction in closure. |
| upstream evidence is missing | Refuse misleading closure and record caveat. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| producing missing runtime proof | Not owned; earlier runtime stages or reruns must supply it. |
| changing product acceptance threshold | Not owned by finalizer implementation. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| final output cannot explain trust boundaries | Requires stronger closure packet or operator truth surface. |
| repeated final harmonization masks upstream weakness | Requires upstream stage contract or blocker-family repair. |
