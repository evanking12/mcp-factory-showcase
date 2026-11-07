 # Product Positioning

## Purpose

This document preserves the current product-positioning, competitive-framing,
and claim-boundary truth for MCP Factory.

It exists so product language, market claims, and research comparisons do not
live only in transient chat.

## Product Identity

Primary identity:

- `legacy interface recovery engine for modern automation`

Do not lead with:

- `reverse-engineering tool`
- `decompiler`
- `universal legacy modernization platform`

Why:

- the budget-bearing value is not analysis for its own sake
- the value is turning undocumented legacy software into callable,
  reviewable, automation-ready interfaces

## Primary Buyer Pain

The dominant enterprise pain for undocumented legacy software is
**operational dependency on tribal knowledge**, not integration friction.

Market signal (Gartner Peer Community poll, April 2026):

**Overall (n=41):**
- Operational dependency on tribal knowledge: **71%**
- Integrating the system with modern tools or workflows: 32%
- Safe testing and change validation: 17%
- Understanding runtime behavior: 7%

**By Role:**
- Director (n=19): tribal knowledge **73%**, integration 18%, safe testing 4%, runtime 4%
- VP (n=3): tribal knowledge 50%, integration 25%, runtime 25%, safe testing 0%
  - VP sample too small to draw conclusions from

Director is the largest role segment and the strongest signal.
Primary target role confirmed: Director of IT.

**By Company Size:**
- Over 10,000 employees (n=8): tribal knowledge **63%**, integration 18%, safe testing 9%, runtime 9%

**By Industry:**
- Finance, Banking & Insurance (n=8): tribal knowledge **72%**, integration 18%, runtime 9%, safe testing 0%
- Manufacturing (n=7): tribal knowledge **55%**, safe testing 23%, integration 11%, runtime 11%

Industry notes:
- Finance: 72% tribal knowledge, 0% safe testing - concern is purely
  knowledge loss, not validation. Strongest vertical signal so far.
- Manufacturing: tribal knowledge still wins at 55% but safe testing
  jumps to 23% vs 9% overall. Factory floor and operational technology
  systems cannot be tested on production - distinct secondary concern
  and a potential vertical-specific messaging angle.

What this means for positioning:

- the primary buying trigger is a **succession or continuity risk event**:
  the person who knows how to run the system is leaving, retiring, or
  already gone, and the operational knowledge lives in their head
- MCP Factory recovers that callable interface surface and makes it
  durable, reviewable, and machine-readable before it walks out the door
- the integration and automation value (MCP server generation) is the
  second-layer benefit that arrives after the knowledge is preserved

Do not invert this order in buyer-facing framing:

- lead with: continuity risk, key-person risk, operational succession
- follow with: automation-ready callable interfaces, integration readiness

The "safe testing and change validation" concern (18%) is downstream of
the tribal knowledge problem. You cannot safely test or validate what you
do not understand. MCP Factory's artifact-rich proving workflow addresses
this as a consequence of surface recovery, not as a separate product.

Unsafe variants to avoid under this framing:

- "we capture all organizational knowledge"
- "we replace the expert who left"

Stay scoped to the **operational callable surface** of the software, not
the full institutional memory of an organization.

## Current Proof Boundary

What is proven today:

- Windows-first legacy callable surface recovery
- callable-surface discovery across undocumented software
- semantic probing and schema synthesis
- MCP wrapper generation
- governed multi-pass execution with durable review and trust surfaces

What is the next expansion band:

- `.NET`
- `COM`

What is strategic but not yet proven:

- `COBOL`
- broader mainframe modernization

Current product truth is narrower than the long-term vision.

That is acceptable.

The right external framing is:

- narrower proof
- real operational value
- explicit next expansion band
- no implied proof beyond current evidence

## Adjacent Research And Why MCP Factory Differs

### DynPRE

What it is:

- protocol reverse engineering through dynamic inference
- active interaction and probe-based protocol learning

Why it matters:

- it validates active probing as a serious reverse-engineering technique

Why MCP Factory is different:

- MCP Factory is not limited to protocol structure inference
- the product target is broader operational interface recovery from legacy
  callable surfaces
- the intended output is an agent-usable interface, not only protocol insight

### LLM4Decompile

What it is:

- LLM-assisted binary decompilation
- focused on producing higher-quality recovered code

Why it matters:

- it validates that LLMs can materially assist reverse-engineering workflows

Why MCP Factory is different:

- MCP Factory is not optimizing primarily for recovered source quality
- it is optimizing for usable operational access:
  - discover callable surfaces
  - infer semantics
  - generate wrappers
  - preserve trust-bearing artifacts

### SEI Legacy Modernization Survey

What it is:

- enterprise modernization framing
- wrapping, componentization, migration, and containment patterns

Why it matters:

- it validates the business problem and the legitimacy of the category

Why MCP Factory is different:

- the survey frames organizational strategies
- MCP Factory aims to automate part of the hard execution layer underneath
  those strategies, especially interface recovery and wrapper creation

### XMainframe

What it is:

- a COBOL or mainframe-focused model and benchmark surface

Why it matters:

- it validates that LLM-assisted legacy modernization is an active research
  area

Why MCP Factory is different:

- XMainframe is not an end-to-end operational interface recovery system
- MCP Factory is currently stronger on Windows-first legacy callable surfaces
- COBOL remains strategic territory for MCP Factory, not current product proof

## Strongest Differentiation

The strongest differentiation is not only:

- full-chain recovery

It is:

- full-chain recovery plus governed operationalization

Meaning:

- interface discovery
- semantic probing
- wrapper generation
- trust-bearing artifacts
- bounded multi-agent execution
- dynamic prompt continuation
- reviewability across repeated passes

Adjacent research artifacts may validate important pieces of the problem, but
they are not the same as a working operational system that can be run,
reviewed, and improved against live output quality.

This governed operationalization layer is a meaningful part of the moat.

## Safe Claims

Safe:

- there is substantial research on reverse engineering, protocol inference,
  decompilation, and legacy modernization
- most adjacent work covers pieces of the problem, not the same operational
  system
- MCP Factory aims to automate discovery, semantic inference, and wrapper
  generation end to end
- the current proof is strongest on Windows-first legacy callable surfaces
- `.NET` and `COM` are the next aligned expansion band
- `COBOL` is strategically relevant but not yet a proven delivery surface
- the product value is reduced reverse-engineering cost, faster interface
  recovery, and improved automation readiness

## Unsafe Claims

Unsafe:

- `nothing like this exists in any form`
- `we solve COBOL modernization today`
- `we can modernize any legacy system`
- `we replace reverse engineers`
- `we are already a universal legacy modernization platform`

These claims create avoidable credibility risk because they outrun current
proof.

## How To Talk About COBOL

Good:

- the same business pain exists in COBOL and mainframe-heavy estates
- COBOL is a strategic expansion area
- the current proof is strongest on Windows-first legacy callable surfaces
- the honest next step is a bounded proof against real customer artifacts

Bad:

- implying that COBOL is already product-mature
- implying direct mainframe modernization capability without evidence
- letting the broader strategic story replace the current proof boundary

## CIO-Safe Framing

Preferred framing:

- undocumented legacy software is a **succession and continuity risk**:
  when the person who knows how to run it leaves, the operational knowledge
  leaves with them
- MCP Factory recovers the callable interface surface of that software and
  makes it durable and reviewable before it becomes a crisis
- the integration and automation readiness (MCP server generation) is the
  downstream benefit once the surface is recovered and documented
- the product should be evaluated first on a bounded, high-value pilot
  against one system where the key-person risk is real and near-term

Do not force the buyer to accept the broadest story first.

Lead with:

- a narrow pain (one system, one key person, one continuity risk)
- a narrow proof surface
- a narrow pilot

The target buyer persona is the IT director or CIO who:

- depends on 2-3 business-critical systems that nobody has touched in years
- has one expert who is retiring or planning to leave within 18 months
- cannot safely upgrade or integrate that system because the "how it works"
  knowledge is not written down anywhere

This persona is not shopping for AI or MCP. They are buying insurance
against operational knowledge loss. Frame accordingly.

## References

- DynPRE:
  - [NDSS page](https://www.ndss-symposium.org/ndss-paper/dynpre-protocol-reverse-engineering-via-dynamic-inference/)
- LLM4Decompile:
  - [arXiv](https://arxiv.org/abs/2403.05286)
- A Survey of Legacy System Modernization Approaches:
  - [SEI](https://www.sei.cmu.edu/library/a-survey-of-legacy-system-modernization-approaches/)
- XMainframe:
  - [arXiv](https://arxiv.org/abs/2408.04660)
- Gartner Peer Community poll (April 2026, n=41):
  - question: "When dealing with business-critical but undocumented legacy
    software, where does the biggest cost/risk usually sit first?"
  - overall: tribal knowledge 71%, integration 32%, safe testing 17%,
    runtime behavior 7%
  - Director segment (n=19): tribal knowledge 73%
  - Finance/Banking/Insurance (n=8): tribal knowledge 72%
  - Manufacturing (n=7): tribal knowledge 55%, safe testing 23%
  - implication: primary buyer pain is succession and continuity risk, not
    integration friction; Director of IT is primary target role; Finance
    and Manufacturing are strongest verticals so far
  - see Primary Buyer Pain section above for full segmentation
