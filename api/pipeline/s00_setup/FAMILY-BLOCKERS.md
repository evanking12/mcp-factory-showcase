# S-00 Family Blockers

S-00 owns setup/static-prior preparation. It should classify recurring blockers
here instead of leaving them in chat or broad campaign memory.

## handles

| Blocker family | Stage stance |
| --- | --- |
| missing static strings | Handle when binary bytes are available; otherwise record ambiguity and preserve compatibility. |
| sentinel/error-code baseline missing | Calibrate or seed sentinels when possible. |
| vocab seed too thin | Seed from signatures, hints, use cases, and prior context when available. |

## detects_and_defers

| Blocker family | Stage stance |
| --- | --- |
| thin Ghidra/static surface | Record admission risk and pass bounded context forward. |
| runtime precondition unknown | Defer to S-01 unlock and S-02 probing. |
| callable dependency hints without proof | Pass as prior hints, not truth. |

## unknown_or_not_owned

| Blocker family | Stage stance |
| --- | --- |
| cross-DLL dependency | Not owned in current S-00; requires a later cross-DLL admission layer. |
| runtime side effect sequencing | Not owned; downstream runtime stages must prove it. |

## architecture_gap

| Blocker family | Stage stance |
| --- | --- |
| packet too rich for S-01 | Requires coordinator/admission discipline rather than dumping raw static richness downstream. |
| repeated static ambiguity with no admission signal | Requires stronger packet review or stage stay/fail criteria. |
