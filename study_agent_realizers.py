#!/usr/bin/env python3
"""
Domain-Adaptive Realizer Layer — v4

Two-layer generation architecture:
  Layer 1: Universal archetype library (10 archetypes, defined by cognitive operation)
  Layer 2: Domain-adaptive realization (course-family-specific vocabulary and framing)

Phase 1 fully implemented: GenericRealizer, EconCausalRealizer, MathRealizer, CSRealizer
Phase 1 stubbed (delegates to Generic): EconPriceRealizer, AccountingRealizer,
  BiologyRealizer, ChemistryRealizer, HumanitiesRealizer
"""

from __future__ import annotations

import math
import re
from typing import Any


# ---------------------------------------------------------------------------
# Archetype definitions (10 universal archetypes)
# ---------------------------------------------------------------------------

ARCHETYPE_DEFINITIONS: dict[int, dict[str, str]] = {
    0: {"name": "Define-in-Context",    "cognitive_op": "Recall + situate",              "output_type": "Definition + example in context"},
    1: {"name": "Compute-and-Interpret","cognitive_op": "Execute procedure + explain",   "output_type": "Numeric answer + interpretation"},
    2: {"name": "Diagnose-Flaw",        "cognitive_op": "Identify violated assumption",  "output_type": "Named flaw + correction"},
    3: {"name": "Apply-Procedure",      "cognitive_op": "Execute multi-step method",     "output_type": "Step-by-step solution"},
    4: {"name": "Interpret-Output",     "cognitive_op": "Read result, extract meaning",  "output_type": "Written interpretation"},
    5: {"name": "Compare-Contrast",     "cognitive_op": "Distinguish two related concepts","output_type": "Structured comparison"},
    6: {"name": "What-If",              "cognitive_op": "Trace downstream effect",       "output_type": "Causal chain"},
    7: {"name": "Synthesize",           "cognitive_op": "Connect >=2 concepts",          "output_type": "Integrated explanation"},
    8: {"name": "Design-or-Evaluate",   "cognitive_op": "Propose or assess a method",   "output_type": "Justified recommendation"},
    9: {"name": "Choose-Tool",          "cognitive_op": "Select appropriate method",     "output_type": "Choice + rationale"},
}

# Flaw types used by archetype 2 across all realizers
FLAW_TYPES: list[str] = [
    "overgeneralization",
    "confounding",
    "circular reasoning",
    "false equivalence",
    "ignoring base rate",
    "measurement error",
    "sampling bias",
]


def _topic_key(topic: str) -> str:
    """Normalize topic string to a short key for structure_signature."""
    k = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    return k[:32]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class DomainRealizer:
    """Abstract base realizer. All realizers implement frame_problem()."""
    family: str = "GENERIC"

    def frame_problem(
        self,
        topic: str,
        archetype_id: int,
        seed: int,
        peers: list[str] | None = None,
        context_signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def supports_computational(self, archetype_id: int) -> bool:
        return archetype_id in {1, 3}

    def _arch_name(self, archetype_id: int) -> str:
        return ARCHETYPE_DEFINITIONS.get(archetype_id, {}).get("name", "unknown")

    def _sig(self, archetype_id: int, variant_id: int, topic: str) -> str:
        return f"{self.family.lower()}:{archetype_id}:{variant_id}:{_topic_key(topic)}"

    def _peer(self, topic: str, peers: list[str] | None, seed: int) -> str:
        pl = [p for p in (peers or []) if p.lower() != topic.lower()]
        if not pl:
            return "a related concept covered in this course"
        return pl[seed % len(pl)]

    def _flaw(self, seed: int) -> str:
        return FLAW_TYPES[seed % len(FLAW_TYPES)]


# ---------------------------------------------------------------------------
# GenericRealizer — 3 variants per archetype = 30 templates
# Priority: high quality, domain-neutral, no invented domain specifics.
# ---------------------------------------------------------------------------

class GenericRealizer(DomainRealizer):
    """
    Domain-neutral realizer used as fallback for all unrecognized course families
    and as the base for Phase 1 stub realizers.

    Design rules:
    - Topic name appears explicitly in the first sentence of every stem.
    - No domain-specific numbers, equations, or named laws are fabricated.
    - Archetype 2 (Diagnose-Flaw) always embeds a concrete stated flaw from FLAW_TYPES.
    - Archetype 6 (What-If) always specifies a concrete hypothetical change and
      requires directionality in the answer (increases / decreases / ambiguous).
    - Peer topics used for archetypes 5 (most-distant) and 7 (most-adjacent).
    """
    family: str = "GENERIC"

    def frame_problem(
        self,
        topic: str,
        archetype_id: int,
        seed: int,
        peers: list[str] | None = None,
        context_signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        variant_id = seed % 3
        a = archetype_id
        name = topic

        # Peer selection: most-distant = peers[0], most-adjacent = peers[-1]
        peers_list = [p for p in (peers or []) if p.lower() != name.lower()]
        distant_peer = peers_list[0] if peers_list else "a related concept from this course"
        adjacent_peer = peers_list[-1] if peers_list else "a closely related concept"
        flaw = self._flaw(seed)

        result = self._generate(a, variant_id, name, distant_peer, adjacent_peer, flaw, seed)
        result["archetype_id"]       = a
        result["archetype"]          = a
        result["archetype_name"]     = self._arch_name(a)
        result["structure_signature"] = self._sig(a, variant_id, name)
        result["generator"]          = "generic"
        result["realizer_family"]    = self.family
        result["topic"]              = name
        return result

    def _generate(
        self,
        a: int,
        v: int,
        name: str,
        distant_peer: str,
        adjacent_peer: str,
        flaw: str,
        seed: int,
    ) -> dict[str, Any]:

        # ── Archetype 0: Define-in-Context ────────────────────────────────
        if a == 0:
            if v == 0:
                stem = (
                    f"Define {name} in your own words, then situate it within the broader "
                    f"framework of this course.\n\n"
                    f"(a) Provide a precise definition that distinguishes {name} from "
                    f"related concepts.\n"
                    f"(b) Give one concrete example from course material that illustrates "
                    f"the definition.\n"
                    f"(c) Explain why {name} matters — what would be harder to understand "
                    f"or do without it?"
                )
                answer = (
                    f"(a) Must state what {name} is, not just what it does. A strong definition "
                    f"identifies the core property that separates it from adjacent concepts. "
                    f"(b) Example must be specific to course context, not generic. "
                    f"(c) Should articulate a real analytical or practical consequence, not a tautology."
                )
                steps = [
                    f"State the core definition of {name} — what it is, not what it does.",
                    "Name a course-specific example and connect it to the definition.",
                    "Explain what understanding {name} enables that would otherwise be unavailable.",
                ]
            elif v == 1:
                stem = (
                    f"A student encounters {name} for the first time and asks: "
                    f"\"What is this, and when would I use it?\"\n\n"
                    f"Write a response that:\n"
                    f"(a) Defines {name} clearly enough for the student to recognize it in "
                    f"a new problem.\n"
                    f"(b) Describes the conditions under which {name} applies.\n"
                    f"(c) Identifies one situation where a similar-sounding concept would be "
                    f"used instead, and explains the difference."
                )
                answer = (
                    f"(a) Definition should be recognition-ready — someone who reads it can spot "
                    f"{name} in an unfamiliar context. "
                    f"(b) Conditions should specify what must be true for {name} to apply. "
                    f"(c) Contrast must name a specific alternative, not just say 'other methods.'"
                )
                steps = [
                    f"Define {name} in terms a first-time reader can act on.",
                    "State the conditions: when does {name} apply vs. not apply?",
                    "Name one closely related concept and state the distinguishing criterion.",
                ]
            else:  # v == 2
                stem = (
                    f"Consider the following claim about {name}:\n\n"
                    f"\"Understanding {name} is mainly a matter of knowing its definition.\"\n\n"
                    f"(a) Agree or disagree — with a specific argument, not a vague hedge.\n"
                    f"(b) Provide a definition of {name} that demonstrates the distinction "
                    f"between knowing the term and understanding the concept.\n"
                    f"(c) Give one example where knowing the definition without deeper "
                    f"understanding would lead to a wrong answer."
                )
                answer = (
                    f"(a) Disagreement is the defensible position: definitions are entry points, "
                    f"not endpoints. (b) A strong definition includes the conditions, not just the label. "
                    f"(c) Failure mode must be specific — a case where surface-level recall fails."
                )
                steps = [
                    f"Take a clear position on whether definition-level knowledge is sufficient for {name}.",
                    "Provide a definition that encodes deeper understanding, not just the term.",
                    "Construct a concrete case where definition alone produces the wrong answer.",
                ]
            concept = f"Archetype 0: Define-in-Context — {name}"

        # ── Archetype 1: Compute-and-Interpret ───────────────────────────
        elif a == 1:
            # Use symbolic values to avoid inventing domain-specific constants
            X = 40 + (seed % 30)
            Y = 10 + (seed % 15)
            ratio = round(X / Y, 2)
            if v == 0:
                stem = (
                    f"You are given the following values related to {name}:\n\n"
                    f"  Value A = {X},   Value B = {Y}\n\n"
                    f"(a) Compute the ratio A/B and state what it represents in the context "
                    f"of {name}.\n"
                    f"(b) If Value B increased by 50%, compute the new ratio and explain "
                    f"qualitatively how the interpretation changes.\n"
                    f"(c) What assumption about the measurement of A and B must hold for "
                    f"this ratio to be meaningful?"
                )
                answer = (
                    f"(a) A/B = {ratio}. Interpretation depends on what A and B represent — "
                    f"students must connect the number to {name}, not just divide. "
                    f"(b) New B = {round(Y * 1.5, 1)}; new ratio = {round(X / (Y * 1.5), 2)}. "
                    f"Interpretation shifts accordingly. "
                    f"(c) Key assumption: A and B must be measured on comparable scales/units."
                )
                steps = [
                    f"Compute A/B = {X}/{Y} = {ratio}.",
                    f"Compute new ratio with B * 1.5 = {round(Y * 1.5, 1)}.",
                    "State the measurement assumption — units, comparability, or independence.",
                ]
            elif v == 1:
                diff = X - Y
                pct_change = round((diff / Y) * 100, 1)
                stem = (
                    f"In a study involving {name}, the baseline measure is {Y} and the "
                    f"observed measure is {X}.\n\n"
                    f"(a) Calculate the absolute difference and the percentage change.\n"
                    f"(b) A colleague says the {pct_change}% change is 'large.' "
                    f"What additional information would you need to evaluate that claim?\n"
                    f"(c) Suppose the baseline were cut in half. Without recalculating, "
                    f"explain how the percentage change would shift and why."
                )
                answer = (
                    f"(a) Absolute diff = {diff}; % change = ({diff}/{Y}) × 100 = {pct_change}%. "
                    f"(b) Need: baseline variability, comparison group, practical significance threshold. "
                    f"(c) Smaller baseline → larger % change for same numerator (denominator shrinks)."
                )
                steps = [
                    f"Absolute diff = {X} - {Y} = {diff}.",
                    f"Pct change = {diff}/{Y} × 100 = {pct_change}%.",
                    "Assess 'large' by referencing variability and practical context.",
                ]
            else:  # v == 2
                Z = X + Y
                stem = (
                    f"Three measurements related to {name} are recorded: "
                    f"A = {X}, B = {Y}, Total = {Z}.\n\n"
                    f"(a) Compute A as a share of Total and B as a share of Total.\n"
                    f"(b) Verify that the shares sum correctly and explain what this check tells you.\n"
                    f"(c) If Total were measured with error (say, ±5%), characterize how "
                    f"that uncertainty propagates to the shares."
                )
                share_a = round(X / Z, 3)
                share_b = round(Y / Z, 3)
                answer = (
                    f"(a) Share A = {X}/{Z} = {share_a}; Share B = {Y}/{Z} = {share_b}. "
                    f"(b) Shares sum ≈ {round(share_a + share_b, 3)} — should equal 1.0; "
                    f"rounding may cause small deviation. "
                    f"(c) ±5% error in Total → ±5% error in each share (denominators move together)."
                )
                steps = [
                    f"Share A = {X}/{Z} = {share_a}.",
                    f"Share B = {Y}/{Z} = {share_b}.",
                    "Trace ±5% Total error through the share formula.",
                ]
            concept = f"Archetype 1: Compute-and-Interpret — {name}"

        # ── Archetype 2: Diagnose-Flaw ────────────────────────────────────
        elif a == 2:
            if v == 0:
                stem = (
                    f"A researcher studying {name} reaches the following conclusion:\n\n"
                    f"\"Since the observed pattern is consistent with {name}, the relationship "
                    f"must be causal.\"\n\n"
                    f"(a) Identify the specific logical error in this reasoning "
                    f"(the flaw is: {flaw}).\n"
                    f"(b) Explain why this error matters — what alternative explanation does "
                    f"it fail to rule out?\n"
                    f"(c) Describe one additional piece of evidence that would help distinguish "
                    f"the causal interpretation from the alternative."
                )
                answer = (
                    f"(a) The flaw is {flaw}: consistency with a hypothesis does not establish it. "
                    f"(b) The alternative is that a third factor (or reverse causation) produces "
                    f"the same pattern without the claimed mechanism. "
                    f"(c) Evidence should vary the proposed cause while holding alternatives constant."
                )
                steps = [
                    f"Name the flaw: {flaw}.",
                    "State the alternative explanation the researcher ignores.",
                    "Propose a discriminating test or piece of evidence.",
                ]
            elif v == 1:
                stem = (
                    f"A student submits the following interpretation of {name}:\n\n"
                    f"\"The data shows a large effect, so we can conclude the result is "
                    f"both statistically significant and practically important.\"\n\n"
                    f"(a) Identify the logical error in conflating these two claims "
                    f"(the flaw is: {flaw}).\n"
                    f"(b) Provide a concrete example where the effect is statistically "
                    f"significant but practically trivial, or vice versa.\n"
                    f"(c) What should the student report instead to avoid this error?"
                )
                answer = (
                    f"(a) The flaw is {flaw}: statistical significance and practical importance "
                    f"are distinct — significance depends on sample size, importance on effect magnitude. "
                    f"(b) Large N → tiny effect can be significant; small N → large effect may not be. "
                    f"(c) Report effect size and confidence interval alongside the p-value."
                )
                steps = [
                    f"Name the flaw: {flaw}.",
                    "Construct a counter-example with mismatched significance and importance.",
                    "State the corrected reporting approach.",
                ]
            else:  # v == 2
                stem = (
                    f"A report on {name} concludes:\n\n"
                    f"\"Because our sample showed this result, the same result holds for "
                    f"the population from which the sample was drawn.\"\n\n"
                    f"(a) Identify the specific inferential flaw (the flaw is: {flaw}).\n"
                    f"(b) List two conditions that must hold for the inference to be valid.\n"
                    f"(c) Explain how you would check whether those conditions hold using "
                    f"information available before the study was conducted."
                )
                answer = (
                    f"(a) The flaw is {flaw}: samples support population inference only when "
                    f"sampling was representative and the sample was large enough. "
                    f"(b) Required: (i) random or representative sampling, (ii) adequate sample size. "
                    f"(c) Pre-study: review sampling protocol and power calculation."
                )
                steps = [
                    f"Name the flaw: {flaw}.",
                    "State the two conditions for valid population inference.",
                    "Describe the pre-study checks that would verify each condition.",
                ]
            concept = f"Archetype 2: Diagnose-Flaw — flaw type: {flaw}"

        # ── Archetype 3: Apply-Procedure ──────────────────────────────────
        elif a == 3:
            if v == 0:
                stem = (
                    f"Apply the procedure associated with {name} to the following situation:\n\n"
                    f"You have two groups (A and B). Group A has measure = {40 + seed % 20}, "
                    f"Group B has measure = {25 + seed % 15}. Sample sizes are equal.\n\n"
                    f"(a) State the procedure you will use and why it is appropriate here.\n"
                    f"(b) Execute the procedure step by step.\n"
                    f"(c) Interpret the result — what does it tell you, and what does it not tell you?"
                )
                answer = (
                    f"(a) Procedure: apply {name}. Appropriate because the setup satisfies [conditions]. "
                    f"(b) Execute: compute difference, assess magnitude, check assumptions. "
                    f"(c) Result tells you [directional claim]; it does not establish [limitation]."
                )
                steps = [
                    f"State which procedure {name} involves and confirm the setup meets its conditions.",
                    "Execute step by step — show intermediate values.",
                    "State one thing the result confirms and one thing it cannot confirm.",
                ]
            elif v == 1:
                stem = (
                    f"You have been asked to apply {name} to analyze data from a study. "
                    f"Before running the analysis, you must verify three conditions.\n\n"
                    f"(a) List the three conditions and explain why each is required.\n"
                    f"(b) For each condition, describe a diagnostic check you would run.\n"
                    f"(c) If one condition fails, explain what adjustment or alternative "
                    f"procedure is available."
                )
                answer = (
                    f"(a) Conditions depend on {name}'s assumptions — typically involve "
                    f"independence, distributional requirements, and measurement validity. "
                    f"(b) Diagnostics: inspection, formal tests, or sensitivity checks. "
                    f"(c) Failure → robust alternative or assumption-correcting transformation."
                )
                steps = [
                    f"List {name}'s three core assumptions with justification.",
                    "Pair each assumption with a concrete diagnostic check.",
                    "Name the fallback procedure if one assumption fails.",
                ]
            else:  # v == 2
                stem = (
                    f"A colleague applies {name} to a dataset and gets result R. "
                    f"They then apply the same procedure to a modified dataset (one variable "
                    f"multiplied by 2) and get result 2R.\n\n"
                    f"(a) Is this expected behavior? Justify with reference to the procedure's properties.\n"
                    f"(b) Identify one transformation that would NOT scale the result in the "
                    f"same way, and explain why.\n"
                    f"(c) What does this tell you about using {name} with differently scaled variables?"
                )
                answer = (
                    f"(a) Depends on whether {name} is scale-invariant or scale-equivariant. "
                    f"Linear procedures often scale proportionally; normalized ones do not. "
                    f"(b) Logarithmic or rank-based transformation would not double the result. "
                    f"(c) Scaling matters — always standardize variables before comparing results."
                )
                steps = [
                    f"Determine whether {name} is scale-invariant or scale-equivariant.",
                    "Name a transformation that breaks the doubling behavior.",
                    "State the practical implication for variable scaling.",
                ]
            concept = f"Archetype 3: Apply-Procedure — {name}"

        # ── Archetype 4: Interpret-Output ─────────────────────────────────
        elif a == 4:
            val = 0.62 + round((seed % 20) / 100, 2)
            if v == 0:
                stem = (
                    f"An analysis involving {name} produces the following output:\n\n"
                    f"  Result: {val}   (95% interval: [{round(val - 0.15, 2)}, {round(val + 0.15, 2)}])\n\n"
                    f"(a) Interpret this result in plain language — what does {val} mean?\n"
                    f"(b) Based on the interval, what can you conclude about precision? "
                    f"What cannot be concluded?\n"
                    f"(c) A reader claims this result 'proves' the underlying relationship. "
                    f"Identify the error in that interpretation."
                )
                answer = (
                    f"(a) {val} represents [the magnitude of the relationship described by {name}]. "
                    f"(b) Interval width = 0.30 — moderate precision. Cannot conclude the true value "
                    f"is exactly {val}. (c) Error: results provide evidence, not proof; "
                    f"alternative explanations remain."
                )
                steps = [
                    f"State in one sentence what {val} represents in the context of {name}.",
                    "Characterize precision from the interval width.",
                    "Explain why 'evidence' ≠ 'proof' for this type of result.",
                ]
            elif v == 1:
                stem = (
                    f"Two analyses of {name} produce different outputs:\n\n"
                    f"  Analysis 1: result = {val}\n"
                    f"  Analysis 2: result = {round(val * 0.6, 2)}\n\n"
                    f"(a) Propose two methodological reasons the results could legitimately differ.\n"
                    f"(b) Which result should you trust more, and what information would "
                    f"you need to make that judgment?\n"
                    f"(c) What would you report to a non-technical audience, and why?"
                )
                answer = (
                    f"(a) Differences can arise from: different samples, different specifications, "
                    f"different variable definitions, or different estimation methods. "
                    f"(b) Trust depends on sample quality, specification validity, pre-registration. "
                    f"(c) Report the range and explain why results vary — do not cherry-pick."
                )
                steps = [
                    "List two methodological sources of divergence.",
                    "State what information determines which result to trust.",
                    "Draft a one-sentence non-technical description of the range.",
                ]
            else:  # v == 2
                stem = (
                    f"An output from an analysis of {name} shows the result changed from "
                    f"{round(val * 0.8, 2)} to {val} after adding a control variable.\n\n"
                    f"(a) Interpret what this change suggests about the original analysis.\n"
                    f"(b) Does the change make the new estimate more or less trustworthy? Explain.\n"
                    f"(c) What additional controls would you consider, and how would you "
                    f"decide when to stop adding them?"
                )
                answer = (
                    f"(a) The change suggests the omitted variable was correlated with both "
                    f"the treatment and the outcome — a form of confounding. "
                    f"(b) New estimate is generally more trustworthy if the added variable "
                    f"is a valid confounder, not a collider. "
                    f"(c) Add variables on theoretical grounds; stop when coefficient stabilizes "
                    f"and adding more does not change interpretation."
                )
                steps = [
                    f"Explain what the shift from {round(val*0.8,2)} to {val} implies about confounding.",
                    "State the condition under which adding the control improves (vs. harms) the estimate.",
                    "Describe the stopping rule for adding controls.",
                ]
            concept = f"Archetype 4: Interpret-Output — {name}"

        # ── Archetype 5: Compare-Contrast ─────────────────────────────────
        elif a == 5:
            peer = distant_peer  # most-distant peer for sharpest contrast
            if v == 0:
                stem = (
                    f"Compare and contrast {name} and {peer}.\n\n"
                    f"(a) State the defining feature of each concept — what makes each "
                    f"what it is, rather than the other.\n"
                    f"(b) Describe one situation where you would use {name} and one where "
                    f"you would use {peer}. What feature of the situation determines the choice?\n"
                    f"(c) Identify one common misconception that confuses the two, and "
                    f"explain how to avoid it."
                )
                answer = (
                    f"(a) {name}: [core feature]; {peer}: [core feature]. The distinction must "
                    f"be structural, not just descriptive. "
                    f"(b) Situation determines choice based on [key discriminating criterion]. "
                    f"(c) Misconception usually involves confusing surface features with "
                    f"structural ones."
                )
                steps = [
                    f"Define {name} and {peer} by their distinguishing structural property.",
                    "Pair each with a situation where it applies; name the discriminating criterion.",
                    "State the common misconception and the conceptual fix.",
                ]
            elif v == 1:
                stem = (
                    f"A student claims that {name} and {peer} are 'basically the same thing '.\n\n"
                    f"(a) Identify the specific way in which they are similar (so the student "
                    f"is not entirely wrong).\n"
                    f"(b) Identify the specific way in which they differ (the distinction "
                    f"that makes calling them 'the same' incorrect).\n"
                    f"(c) Give an example where treating them as the same would produce "
                    f"a wrong answer or bad decision."
                )
                answer = (
                    f"(a) Similarity: both relate to [shared property]. "
                    f"(b) Difference: {name} involves [X] while {peer} involves [Y] — "
                    f"this is not a matter of degree. "
                    f"(c) Failure case: applying {name}'s logic in a {peer} context leads to [error]."
                )
                steps = [
                    f"Grant the similarity: what do {name} and {peer} share?",
                    "State the irreducible difference.",
                    "Construct the failure case where the confusion matters.",
                ]
            else:  # v == 2
                stem = (
                    f"Construct a table comparing {name} and {peer} along three dimensions:\n\n"
                    f"  1. What it requires (inputs / assumptions)\n"
                    f"  2. What it produces (outputs / conclusions)\n"
                    f"  3. When it is preferred (conditions favoring its use)\n\n"
                    f"After the table, write one paragraph explaining which you would choose "
                    f"in an ambiguous situation and why."
                )
                answer = (
                    f"Table should have rows for {name} and {peer}, columns for the three dimensions. "
                    f"Paragraph must make a specific choice and justify it based on conditions, "
                    f"not just restate that 'it depends.'"
                )
                steps = [
                    "Fill in the 2×3 table with specific, not vague, entries.",
                    f"Write the disambiguation paragraph: pick one, justify the pick.",
                ]
            concept = f"Archetype 5: Compare-Contrast — {name} vs. {peer}"

        # ── Archetype 6: What-If ──────────────────────────────────────────
        elif a == 6:
            direction_word = ["increases", "decreases", "doubles", "halves"][seed % 4]
            if v == 0:
                stem = (
                    f"Consider a system or context in which {name} plays a key role. "
                    f"Suppose one of the key inputs to this system {direction_word} by a "
                    f"substantial amount.\n\n"
                    f"(a) Trace the downstream effects on {name} step by step — "
                    f"state whether {name} increases, decreases, or is ambiguous.\n"
                    f"(b) Identify one second-order effect (an effect on something connected "
                    f"to {name} that changes as a result of the change in {name}).\n"
                    f"(c) Under what condition would the direction of the effect reverse?"
                )
                answer = (
                    f"(a) Trace the causal chain: input {direction_word} → effect on {name} "
                    f"[increases/decreases/ambiguous]. Students must commit to a direction "
                    f"or justify ambiguity. "
                    f"(b) Second-order: [connected concept] changes in [direction] because [mechanism]. "
                    f"(c) Reversal condition: [boundary case that flips the mechanism]."
                )
                steps = [
                    f"State the direction: does {name} increase, decrease, or is it ambiguous? Justify.",
                    f"Identify one second-order downstream effect.",
                    "State the condition under which the direction reverses.",
                ]
            elif v == 1:
                stem = (
                    f"Suppose a key assumption underlying {name} is relaxed — specifically, "
                    f"assume that [the usual condition] no longer holds.\n\n"
                    f"(a) State the assumption being relaxed and explain what it normally guarantees.\n"
                    f"(b) Trace what happens to {name}'s conclusions when the assumption fails — "
                    f"do they still hold, partially hold, or fail entirely?\n"
                    f"(c) Propose one adjustment to the analysis that could restore validity "
                    f"under the relaxed assumption."
                )
                answer = (
                    f"(a) The assumption [X] normally guarantees [property Y]. "
                    f"(b) Without it, the conclusion [Z] either fails because [mechanism] "
                    f"or is only partially valid in [restricted setting]. "
                    f"(c) Adjustment: [modification to procedure or data collection] restores validity."
                )
                steps = [
                    f"Name the assumption and what it guarantees for {name}.",
                    "Trace what breaks when the assumption fails.",
                    "Propose the adjustment.",
                ]
            else:  # v == 2
                stem = (
                    f"A practitioner is applying {name} when the sample size {direction_word}.\n\n"
                    f"(a) Without performing a calculation, explain qualitatively how this "
                    f"change affects the precision of conclusions drawn from {name}.\n"
                    f"(b) Is there a threshold beyond which further {direction_word} produces "
                    f"diminishing returns? Explain the logic.\n"
                    f"(c) Identify one situation where {direction_word} the sample would not "
                    f"improve the conclusions and explain why."
                )
                answer = (
                    f"(a) Sample size {direction_word} → precision [increases/decreases] "
                    f"because [statistical mechanism]. "
                    f"(b) Diminishing returns: yes, due to square-root relationship between "
                    f"N and standard error. "
                    f"(c) More data does not help when: the sample is biased, the instrument is "
                    f"invalid, or the research question is ill-defined."
                )
                steps = [
                    f"State direction of precision change when N {direction_word}.",
                    "Explain the diminishing-returns threshold.",
                    "Name the situation where more N doesn't help.",
                ]
            concept = f"Archetype 6: What-If — {name}, input {direction_word}"

        # ── Archetype 7: Synthesize ───────────────────────────────────────
        elif a == 7:
            peer = adjacent_peer  # most-adjacent peer for synthesis
            if v == 0:
                stem = (
                    f"Both {name} and {peer} are relevant to the following scenario:\n\n"
                    f"A researcher wants to understand a complex outcome. They have access "
                    f"to observational data and a theoretical framework.\n\n"
                    f"(a) Explain how {name} and {peer} each contribute to the analysis.\n"
                    f"(b) Describe how combining the two produces an insight that neither "
                    f"could provide alone.\n"
                    f"(c) Identify one tension or trade-off between using {name} and "
                    f"{peer} simultaneously."
                )
                answer = (
                    f"(a) {name} contributes [X]; {peer} contributes [Y]. "
                    f"(b) Combined insight: [Z] — this requires seeing both at once. "
                    f"(c) Tension: [conflict between assumptions, goals, or interpretive frames]."
                )
                steps = [
                    f"Assign each concept ({name}, {peer}) a distinct analytical role.",
                    "State the synthesis insight — what emerges from combining them.",
                    "Name the tension.",
                ]
            elif v == 1:
                stem = (
                    f"Use both {name} and {peer} to evaluate the following claim:\n\n"
                    f"\"A single measure is sufficient to characterize the phenomenon "
                    f"of interest.\"\n\n"
                    f"(a) What would {name} say about this claim? (b) What would {peer} say? "
                    f"(c) Synthesize the two perspectives into a single, defensible conclusion "
                    f"that goes beyond what either perspective says alone."
                )
                answer = (
                    f"(a) {name}'s perspective: [position on sufficiency of single measure]. "
                    f"(b) {peer}'s perspective: [different or complementary position]. "
                    f"(c) Synthesis must advance beyond listing both views — it must produce "
                    f"a new claim about when a single measure is and is not adequate."
                )
                steps = [
                    f"State {name}'s stance on the sufficiency claim.",
                    f"State {peer}'s stance.",
                    "Write the synthesis claim — one sentence that neither stance alone entails.",
                ]
            else:  # v == 2
                stem = (
                    f"A policy-maker asks you to brief them on how {name} and {peer} "
                    f"together inform a decision they must make.\n\n"
                    f"(a) Summarize what each concept contributes to the decision.\n"
                    f"(b) Identify the conditions under which each concept should be "
                    f"weighted more heavily.\n"
                    f"(c) Draft a one-paragraph briefing that synthesizes both into "
                    f"actionable guidance — no academic hedging."
                )
                answer = (
                    f"(a) {name} → [contribution]; {peer} → [contribution]. "
                    f"(b) {name} weighted more when [condition]; {peer} when [condition]. "
                    f"(c) Brief must commit to a recommendation, not list considerations."
                )
                steps = [
                    "Assign each concept its contribution to the decision.",
                    "State the conditions that tilt the weighting.",
                    "Write the actionable brief — commit to a recommendation.",
                ]
            concept = f"Archetype 7: Synthesize — {name} + {peer}"

        # ── Archetype 8: Design-or-Evaluate ──────────────────────────────
        elif a == 8:
            if v == 0:
                stem = (
                    f"You are asked to design a study or evaluation that relies on {name}.\n\n"
                    f"(a) Specify the three most important design choices and justify each.\n"
                    f"(b) Identify the single most serious threat to the validity of your "
                    f"design and explain how you would address it.\n"
                    f"(c) A colleague proposes an alternative design that avoids your "
                    f"validity threat but introduces a new one. Evaluate the trade-off."
                )
                answer = (
                    f"(a) Choices should be specific and justified by reference to {name}'s requirements. "
                    f"(b) Validity threat: [specific threat]; mitigation: [specific fix]. "
                    f"(c) Trade-off evaluation must compare threats on the same dimension — "
                    f"which is more likely to bias conclusions?"
                )
                steps = [
                    f"List three design choices for applying {name} — each with a justification.",
                    "Name the validity threat and the mitigation.",
                    "Evaluate the alternative design's trade-off explicitly.",
                ]
            elif v == 1:
                stem = (
                    f"A published study uses {name} but its design has three potential flaws:\n\n"
                    f"  1. The sample was drawn from a convenience population.\n"
                    f"  2. The outcome was measured with a single self-report item.\n"
                    f"  3. No control condition was included.\n\n"
                    f"(a) Evaluate each flaw: how serious is it, and why?\n"
                    f"(b) Which flaw is most damaging to the conclusions? Justify.\n"
                    f"(c) Propose one revision to the design that would address the "
                    f"most damaging flaw at minimum cost."
                )
                answer = (
                    f"(a) Flaw 1 (convenience sample): threatens external validity. "
                    f"Flaw 2 (single item): threatens measurement validity. "
                    f"Flaw 3 (no control): threatens internal validity. "
                    f"(b) No control condition is typically most damaging because it prevents "
                    f"causal inference entirely. "
                    f"(c) Revision: [add matched controls / natural experiment / historical comparison]."
                )
                steps = [
                    "Rate each flaw by which validity type it threatens.",
                    "Rank them and justify the ranking.",
                    "Propose the minimum-cost revision.",
                ]
            else:  # v == 2
                stem = (
                    f"Two teams propose different approaches to studying {name}.\n\n"
                    f"Team A: large observational dataset, sophisticated statistical controls.\n"
                    f"Team B: small randomized experiment, simple analysis.\n\n"
                    f"(a) Evaluate each approach on internal validity and external validity.\n"
                    f"(b) Under what circumstances would you prefer Team A's approach? Team B's?\n"
                    f"(c) Design a hybrid approach that captures the main strength of each."
                )
                answer = (
                    f"(a) Team A: high external validity (large N, real-world); lower internal validity "
                    f"(confounders). Team B: high internal validity (randomization); lower external "
                    f"(small, restricted sample). "
                    f"(b) Prefer A when external validity matters most (policy); B when causal "
                    f"identification matters most (mechanism). "
                    f"(c) Hybrid: randomized trial embedded in a large cohort study."
                )
                steps = [
                    "Score each team on internal and external validity.",
                    "Name the condition that favors each.",
                    "Describe the hybrid design.",
                ]
            concept = f"Archetype 8: Design-or-Evaluate — {name}"

        # ── Archetype 9: Choose-Tool ──────────────────────────────────────
        else:  # a == 9
            peer = distant_peer
            if v == 0:
                stem = (
                    f"You face the following analytical choice: apply {name} or {peer} "
                    f"to a new dataset.\n\n"
                    f"(a) List three criteria that should govern the choice.\n"
                    f"(b) For each criterion, describe what you would look for in the data "
                    f"or context to evaluate it.\n"
                    f"(c) Apply your criteria to this case: the data is small (N=30), "
                    f"the relationship is expected to be non-linear, and you need an "
                    f"easily interpretable result for a non-technical audience. "
                    f"Which approach do you choose, and why?"
                )
                answer = (
                    f"(a) Criteria: sample size suitability, assumption match, interpretability. "
                    f"(b) Evaluate: N against method's minimum requirements; check linearity; "
                    f"assess output complexity. "
                    f"(c) Small N + non-linear + interpretability → {peer} likely preferred unless "
                    f"{name} has non-linear extensions designed for small samples."
                )
                steps = [
                    "State three decision criteria.",
                    "For each, describe what you'd look for in the data.",
                    "Apply the criteria to the described case — commit to a choice.",
                ]
            elif v == 1:
                stem = (
                    f"A colleague automatically applies {name} to every dataset they encounter "
                    f"regardless of context.\n\n"
                    f"(a) Identify two types of datasets where {name} is clearly appropriate "
                    f"and two where it is clearly inappropriate.\n"
                    f"(b) For the inappropriate cases, name the preferred alternative and explain why.\n"
                    f"(c) Draft a one-sentence decision rule your colleague could use to "
                    f"decide whether {name} applies."
                )
                answer = (
                    f"(a) Appropriate: [conditions matching {name}'s assumptions]. "
                    f"Inappropriate: [conditions that violate assumptions]. "
                    f"(b) Alternative for each: [name] because [reason]. "
                    f"(c) Decision rule must be specific and operational — not just 'when appropriate.'"
                )
                steps = [
                    f"List two cases each for appropriate/inappropriate use of {name}.",
                    "Pair each inappropriate case with an alternative and a reason.",
                    "Write the one-sentence decision rule.",
                ]
            else:  # v == 2
                stem = (
                    f"Three analysts independently recommend different methods for studying {name}: "
                    f"Method X, Method Y, and Method Z.\n\n"
                    f"(a) Propose one context in which each recommendation is correct.\n"
                    f"(b) Propose one context in which each recommendation would be wrong.\n"
                    f"(c) Identify the single most important question a researcher should "
                    f"answer before choosing among the three."
                )
                answer = (
                    f"(a) Each method correct in: [contexts where its assumptions are met]. "
                    f"(b) Each method wrong in: [contexts where its assumptions are violated]. "
                    f"(c) Most important question: [the assumption or constraint that discriminates "
                    f"most sharply among the three]."
                )
                steps = [
                    "Assign a 'correct context' to each method.",
                    "Assign a 'wrong context' to each method.",
                    "Name the single most discriminating question.",
                ]
            concept = f"Archetype 9: Choose-Tool — {name} vs. {peer}"

        return {
            "prompt": stem,
            "answer": answer,
            "steps": steps,
            "concept": concept,
            "variant_id": v,
        }


# ---------------------------------------------------------------------------
# EconCausalRealizer — wraps existing specialized generators for comp archetypes
# ---------------------------------------------------------------------------

class EconCausalRealizer(DomainRealizer):
    """
    Realizer for econometrics / causal inference courses.
    Computational archetypes (1, 3) route to specialized generators when the
    topic matches. All other archetypes use causal-inference–flavored conceptual framing.
    """
    family: str = "ECON_CAUSAL"

    # Topics → generator names (mirrors old SPECIALIZED_ARCHETYPE_SUPPORT logic,
    # now internal to this realizer)
    _SPECIALIZED_ARCHETYPES: frozenset[int] = frozenset({1, 3})
    _KEYWORD_MAP: list[tuple[list[str], str]] = [
        (["elasticity"],                          "elasticity"),
        (["total revenue", "revenue"],            "revenue"),
        (["consumer surplus"],                    "consumer_surplus"),
        (["producer surplus"],                    "producer_surplus"),
        (["deadweight", "tax"],                   "deadweight"),
        (["treatment", "experimental", "experiment",
          "potential outcome", "unconfounded",
          "identification", "average treatment"], "treatment_effect"),
        (["accounting", "revenue recognition",
          "inventory", "income statement",
          "balance sheet"],                       "accounting"),
    ]

    def _specialized_generator(self, key: str, generator_name: str):
        """Return the study_agent generator function for the given name."""
        import study_agent as sa  # local import to avoid circular dependency
        mapping = {
            "elasticity":       sa.make_elasticity_problem,
            "revenue":          sa.make_total_revenue_problem,
            "consumer_surplus": sa.make_surplus_problem,
            "producer_surplus": lambda t, s: sa.make_surplus_problem(t, s, producer=True),
            "deadweight":       sa.make_deadweight_loss_problem,
            "treatment_effect": sa.make_treatment_effect_problem,
            "accounting":       sa.make_accounting_problem,
        }
        return mapping.get(generator_name)

    def frame_problem(
        self,
        topic: str,
        archetype_id: int,
        seed: int,
        peers: list[str] | None = None,
        context_signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = topic.lower()
        variant_id = seed % 3

        # Try specialized generators for computational archetypes
        if archetype_id in self._SPECIALIZED_ARCHETYPES:
            for keywords, gen_name in self._KEYWORD_MAP:
                if any(kw in key for kw in keywords):
                    fn = self._specialized_generator(key, gen_name)
                    if fn:
                        try:
                            import study_agent as sa
                            p = fn({"topic": topic, "topic_key": key,
                                    "sources": [], "score": 50}, seed)
                            # Ensure v4 signature format
                            p["structure_signature"] = self._sig(archetype_id, variant_id, topic)
                            p["realizer_family"] = self.family
                            p["archetype_id"] = archetype_id
                            p["archetype"] = archetype_id
                            p["archetype_name"] = self._arch_name(archetype_id)
                            return p
                        except Exception:
                            pass  # Fall through to conceptual

        # Non-computational or no specialized match → use GenericRealizer
        # but with causal-inference vocabulary injected via context
        result = _GENERIC.frame_problem(topic, archetype_id, seed, peers, context_signals)
        result["structure_signature"] = self._sig(archetype_id, variant_id, topic)
        result["realizer_family"] = self.family
        return result


# ---------------------------------------------------------------------------
# MathRealizer — Phase 1 full implementation
# ---------------------------------------------------------------------------

class MathRealizer(DomainRealizer):
    """
    Realizer for mathematics courses (calculus, linear algebra, statistics,
    probability, discrete math, real analysis, etc.).

    Computational archetypes: derivation / calculation framing.
    Conceptual archetypes: proof-style, counterexample, or interpretation framing.
    Archetype 2 (Diagnose-Flaw): proof or argument flaw.
    """
    family: str = "MATH"

    def frame_problem(
        self,
        topic: str,
        archetype_id: int,
        seed: int,
        peers: list[str] | None = None,
        context_signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        a = archetype_id
        v = seed % 3
        name = topic
        flaw = self._flaw(seed)
        peer = self._peer(name, peers, seed)

        result = self._math_frame(a, v, name, peer, flaw, seed)
        result["archetype_id"]        = a
        result["archetype"]           = a
        result["archetype_name"]      = self._arch_name(a)
        result["structure_signature"] = self._sig(a, v, name)
        result["generator"]           = "math"
        result["realizer_family"]     = self.family
        result["topic"]               = name
        return result

    def _math_frame(self, a, v, name, peer, flaw, seed):
        X = 3 + (seed % 7)
        Y = 2 + (seed % 5)

        if a in (1, 3):  # Computational
            if v == 0:
                stem = (
                    f"Let f be a function related to {name} defined by f(x) = x^{X} + {Y}x.\n\n"
                    f"(a) Compute f'(x) using the rules associated with {name}.\n"
                    f"(b) Evaluate f'({Y}) and interpret what this value means geometrically.\n"
                    f"(c) Find the value(s) of x where f'(x) = 0 and classify each as a "
                    f"local min, max, or neither."
                )
                answer = (
                    f"(a) f'(x) = {X}x^{X-1} + {Y}. "
                    f"(b) f'({Y}) = {X * Y**(X-1) + Y} — slope of the tangent at x={Y}. "
                    f"(c) f'(x) = 0 → solve {X}x^{X-1} = -{Y}; classify via second derivative."
                )
                steps = [f"Differentiate f(x) = x^{X} + {Y}x.", f"Evaluate at x={Y}.", "Set f'(x)=0 and classify critical points."]
            elif v == 1:
                stem = (
                    f"Prove or disprove: for {name}, the following statement holds:\n\n"
                    f"\"If condition A is satisfied, then property P follows.\"\n\n"
                    f"(a) State precisely what condition A and property P are in the context "
                    f"of {name}.\n"
                    f"(b) If true, provide a proof sketch (key steps, no full derivation). "
                    f"If false, provide a counterexample.\n"
                    f"(c) Identify the sharpest version of the statement — the weakest "
                    f"condition that still guarantees P."
                )
                answer = (
                    f"(a) Condition and property depend on {name}'s definition. "
                    f"(b) Proof sketch: state the key lemma and how it implies the result. "
                    f"(c) Sharpest version: remove any unnecessary assumptions."
                )
                steps = ["State A and P precisely.", "Prove or counterexample.", "Sharpen the condition."]
            else:
                stem = (
                    f"Compute the following quantity arising in {name}, then analyze sensitivity:\n\n"
                    f"  Q = {X}a + {Y}b,   where a = {seed % 5 + 2},  b = {seed % 3 + 1}\n\n"
                    f"(a) Evaluate Q. (b) If a increases by 1 unit, by how much does Q change? "
                    f"(c) Which variable (a or b) has more leverage over Q, and what does "
                    f"this tell you about {name}?"
                )
                a_val, b_val = seed % 5 + 2, seed % 3 + 1
                Q = X * a_val + Y * b_val
                answer = f"(a) Q = {X}×{a_val} + {Y}×{b_val} = {Q}. (b) ΔQ = {X} per unit ↑ in a. (c) a has more leverage (coefficient {X} > {Y})."
                steps = [f"Evaluate Q = {Q}.", f"dQ/da = {X}.", "Compare coefficients."]

        elif a == 2:  # Diagnose-Flaw (proof/argument flaw)
            stem = (
                f"A student presents the following argument about {name}:\n\n"
                f"\"We know that [premise about {name}]. Therefore, [conclusion] "
                f"follows directly.\"\n\n"
                f"(a) Identify the gap or flaw in this argument (flaw type: {flaw}).\n"
                f"(b) Construct a counterexample that shows the conclusion can fail "
                f"even when the premise holds.\n"
                f"(c) State the additional condition that would make the argument valid."
            )
            answer = (
                f"(a) The flaw is {flaw}: the argument skips a required intermediate step. "
                f"(b) Counterexample: [specific instance where premise holds but conclusion fails]. "
                f"(c) Additional condition: [the missing hypothesis that closes the gap]."
            )
            steps = [f"Identify the logical gap ({flaw}).", "Construct the counterexample.", "State the missing condition."]

        elif a == 5:  # Compare-Contrast
            stem = (
                f"Compare {name} and {peer} as mathematical tools.\n\n"
                f"(a) State the precise mathematical definition of each.\n"
                f"(b) Describe one problem class where {name} applies but {peer} does not, "
                f"and one where the reverse is true.\n"
                f"(c) Identify the deeper mathematical relationship between the two "
                f"(e.g., one generalizes the other, they are dual, they compose, etc.)."
            )
            answer = (
                f"(a) Definitions must be formal — variables, domains, conditions. "
                f"(b) Problem classes should be specific. "
                f"(c) Relationship: [generalization / duality / composition / other]."
            )
            steps = ["State formal definitions.", "Identify each concept's exclusive problem class.", "Name the deeper mathematical relationship."]

        elif a == 6:  # What-If
            stem = (
                f"Consider a key parameter in {name}. Suppose this parameter approaches "
                f"zero (or infinity, as appropriate).\n\n"
                f"(a) State what happens to the central object or formula of {name} "
                f"in this limit — does it increase, decrease, or become undefined?\n"
                f"(b) Is the limit well-defined? If not, explain the obstruction.\n"
                f"(c) Interpret this limiting behavior: what does it tell you about "
                f"when {name} breaks down or becomes degenerate?"
            )
            answer = (
                f"(a) As parameter → [0/∞], the central object [converges to X / diverges / "
                f"becomes undefined]. "
                f"(b) Well-defined if [conditions]; obstruction if [violation]. "
                f"(c) Degenerate case reveals the boundary of {name}'s applicability."
            )
            steps = ["State the limiting behavior.", "Check well-definedness.", "Interpret the degenerate case."]

        else:
            # Delegate remaining archetypes to GenericRealizer
            return _GENERIC._generate(a, seed % 3, name,
                                      peer, peer, self._flaw(seed), seed)

        return {"prompt": stem, "answer": answer, "steps": steps,
                "concept": f"Archetype {a} — {name}", "variant_id": v}


# ---------------------------------------------------------------------------
# CSRealizer — Phase 1 full implementation
# ---------------------------------------------------------------------------

class CSRealizer(DomainRealizer):
    """
    Realizer for computer science courses (algorithms, data structures,
    systems, machine learning, software engineering, etc.).

    Computational archetypes: algorithm trace / complexity analysis.
    Diagnose-Flaw: code or logic flaw.
    What-If: asymptotic behavior change.
    """
    family: str = "CS"

    def frame_problem(
        self,
        topic: str,
        archetype_id: int,
        seed: int,
        peers: list[str] | None = None,
        context_signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        a = archetype_id
        v = seed % 3
        name = topic
        flaw = self._flaw(seed)
        peer = self._peer(name, peers, seed)

        result = self._cs_frame(a, v, name, peer, flaw, seed)
        result["archetype_id"]        = a
        result["archetype"]           = a
        result["archetype_name"]      = self._arch_name(a)
        result["structure_signature"] = self._sig(a, v, name)
        result["generator"]           = "cs"
        result["realizer_family"]     = self.family
        result["topic"]               = name
        return result

    def _cs_frame(self, a, v, name, peer, flaw, seed):
        N = [8, 16, 32][seed % 3]
        K = [2, 3, 4][seed % 3]

        if a in (1, 3):  # Computational — algorithm trace / complexity
            if v == 0:
                stem = (
                    f"Trace the execution of {name} on the following input of size n={N}:\n\n"
                    f"  Input: [show first {min(N,6)} elements of a representative array]\n\n"
                    f"(a) Step through the algorithm, showing state at each major step.\n"
                    f"(b) Count the number of comparisons or operations performed.\n"
                    f"(c) State the time complexity class and justify it from your trace."
                )
                answer = (
                    f"(a) Trace depends on {name}'s specific operations. "
                    f"(b) Operation count for n={N}: [exact or approximate]. "
                    f"(c) Complexity: O([f(n)]) because [the dominant term in the count]."
                )
                steps = ["Trace major steps.", f"Count operations for n={N}.", "Classify complexity from the count."]
            elif v == 1:
                stem = (
                    f"Analyze the time and space complexity of {name}.\n\n"
                    f"(a) State the worst-case, best-case, and average-case time complexity. "
                    f"Justify each.\n"
                    f"(b) State the space complexity. Identify whether it is in-place or requires "
                    f"auxiliary storage.\n"
                    f"(c) Identify the input pattern that triggers worst-case behavior and "
                    f"explain why."
                )
                answer = (
                    f"(a) Worst: O([W]); Best: O([B]); Avg: O([A]). Each justified by [mechanism]. "
                    f"(b) Space: O([S]). In-place if it uses O(1) auxiliary. "
                    f"(c) Worst-case input: [pattern] because it maximizes [the expensive operation]."
                )
                steps = ["State all three time complexities with justifications.", "State space complexity.", "Name the worst-case input pattern."]
            else:
                stem = (
                    f"Compare the complexity of {name} with a naive brute-force approach "
                    f"to the same problem.\n\n"
                    f"(a) State the brute-force complexity and the complexity of {name}.\n"
                    f"(b) For n={N}, compute the approximate number of operations for each.\n"
                    f"(c) At what value of n does {name} become substantially faster? "
                    f"(Define 'substantially' as a {K}× speedup.)"
                )
                answer = (
                    f"(a) Brute-force: O([B]); {name}: O([A]). "
                    f"(b) Brute at n={N}: [approx]; {name} at n={N}: [approx]. "
                    f"(c) {K}× speedup occurs around n=[threshold — solve {K}×A(n)=B(n)]."
                )
                steps = [f"State both complexities.", f"Compute for n={N}.", f"Solve for the {K}× crossover."]

        elif a == 2:  # Diagnose-Flaw — code or logic flaw
            stem = (
                f"A student implements {name} and submits the following logic:\n\n"
                f"```\n"
                f"# Pseudocode\n"
                f"procedure {name.replace(' ','_')}(input):\n"
                f"    result = initial_value\n"
                f"    for each element in input:\n"
                f"        if condition(element):\n"
                f"            result = update(result, element)  # <-- potential flaw here\n"
                f"    return result\n"
                f"```\n\n"
                f"(a) Identify the logical flaw in this implementation "
                f"(flaw type: {flaw}).\n"
                f"(b) Construct a specific input that causes the flaw to produce a wrong answer.\n"
                f"(c) Write the corrected logic and explain what change you made."
            )
            answer = (
                f"(a) The flaw is {flaw}: the update condition or operation is incorrect "
                f"for [specific case]. "
                f"(b) Failing input: [specific example]. "
                f"(c) Fix: [change to update logic or condition]."
            )
            steps = [f"Identify the flaw: {flaw}.", "Construct the failing input.", "State the fix."]

        elif a == 5:  # Compare-Contrast
            stem = (
                f"Compare {name} and {peer}.\n\n"
                f"(a) State the problem each is designed to solve.\n"
                f"(b) Compare their time complexity, space complexity, and any important "
                f"correctness assumptions.\n"
                f"(c) Given a constrained environment (limited memory, real-time deadline, "
                f"or adversarial inputs), which would you choose and why?"
            )
            answer = (
                f"(a) {name} solves [X]; {peer} solves [Y or same problem with different trade-offs]. "
                f"(b) Complexity comparison: [table or list]. "
                f"(c) Choice depends on which constraint is binding — commit to a specific recommendation."
            )
            steps = ["State each algorithm's problem domain.", "Compare complexity + assumptions.", "Choose for the constrained environment."]

        elif a == 6:  # What-If — asymptotic behavior
            stem = (
                f"Consider what happens to {name} as the input size grows without bound.\n\n"
                f"(a) State how the running time of {name} scales with n — "
                f"does it grow faster or slower than linearly?\n"
                f"(b) Suppose the input size doubles. By approximately what factor does "
                f"the runtime increase? Show your reasoning.\n"
                f"(c) Identify one scenario where even this growth rate becomes unacceptable "
                f"and describe an alternative strategy."
            )
            answer = (
                f"(a) {name} scales as O([f(n)]) — [faster/slower/same as linear]. "
                f"(b) Doubling n: runtime multiplied by [f(2n)/f(n)]. "
                f"(c) Unacceptable when [real-time constraint or resource limit]; "
                f"alternative: [approximation / heuristic / problem reduction]."
            )
            steps = ["State the growth rate.", "Compute the doubling factor.", "Name the breaking point and alternative."]

        elif a == 8:  # Design-or-Evaluate
            stem = (
                f"Design a system component that uses {name} as a core building block.\n\n"
                f"(a) Specify the interface (inputs, outputs, guarantees).\n"
                f"(b) Identify the bottleneck: where does {name} become the limiting factor?\n"
                f"(c) Propose one optimization that reduces the bottleneck without changing "
                f"the interface, and analyze its effect on complexity."
            )
            answer = (
                f"(a) Interface: input = [type/constraints], output = [type/guarantee]. "
                f"(b) Bottleneck: [the O(f(n)) step that dominates]. "
                f"(c) Optimization: [caching / precomputation / parallel decomposition]; "
                f"new complexity: [O(g(n))]."
            )
            steps = ["Define the interface.", "Identify the bottleneck step.", "Propose and analyze the optimization."]

        else:
            # Delegate to GenericRealizer for remaining archetypes
            return _GENERIC._generate(a, seed % 3, name,
                                      peer, peer, self._flaw(seed), seed)

        return {"prompt": stem, "answer": answer, "steps": steps,
                "concept": f"Archetype {a} — {name}", "variant_id": v}


# ---------------------------------------------------------------------------
# Phase 1 stub realizers (delegate to GenericRealizer)
# ---------------------------------------------------------------------------

class _StubRealizer(DomainRealizer):
    """Base stub: delegates all framing to GenericRealizer, logs TODO."""
    _TODO_logged: bool = False

    def frame_problem(self, topic, archetype_id, seed, peers=None, context_signals=None):
        result = _GENERIC.frame_problem(topic, archetype_id, seed, peers, context_signals)
        # Override family and signature to the stub's family so routing is visible
        v = seed % 3
        result["structure_signature"] = self._sig(archetype_id, v, topic)
        result["realizer_family"]     = self.family
        result["generator"]           = f"generic_stub_{self.family.lower()}"
        return result


class EconPriceRealizer(_StubRealizer):
    """Phase 1 stub — delegates to Generic. Phase 2: supply/demand/market framing."""
    family = "ECON_PRICE"

class AccountingRealizer(_StubRealizer):
    """Phase 1 stub — delegates to Generic. Phase 2: financial statement framing."""
    family = "ACCOUNTING"

class BiologyRealizer(_StubRealizer):
    """Phase 1 stub — delegates to Generic. Phase 2: mechanism/pathway framing."""
    family = "BIOLOGY"

class ChemistryRealizer(_StubRealizer):
    """Phase 1 stub — delegates to Generic. Phase 2: reaction/equilibrium framing."""
    family = "CHEMISTRY"

class HumanitiesRealizer(_StubRealizer):
    """Phase 1 stub — delegates to Generic. Phase 2: textual/argument framing."""
    family = "HUMANITIES"


# ---------------------------------------------------------------------------
# Module-level singletons (avoid re-instantiation on every call)
# ---------------------------------------------------------------------------

_GENERIC       = GenericRealizer()
_ECON_CAUSAL   = EconCausalRealizer()
_MATH          = MathRealizer()
_CS            = CSRealizer()
_ECON_PRICE    = EconPriceRealizer()
_ACCOUNTING    = AccountingRealizer()
_BIOLOGY       = BiologyRealizer()
_CHEMISTRY     = ChemistryRealizer()
_HUMANITIES    = HumanitiesRealizer()

_FAMILY_MAP: dict[str, DomainRealizer] = {
    "GENERIC":     _GENERIC,
    "ECON_CAUSAL": _ECON_CAUSAL,
    "ECON_PRICE":  _ECON_PRICE,
    "MATH":        _MATH,
    "CS":          _CS,
    "ACCOUNTING":  _ACCOUNTING,
    "BIOLOGY":     _BIOLOGY,
    "CHEMISTRY":   _CHEMISTRY,
    "HUMANITIES":  _HUMANITIES,
}


def get_realizer(family: str) -> DomainRealizer:
    """Factory: return the realizer for the given family, defaulting to GENERIC."""
    return _FAMILY_MAP.get(family.upper(), _GENERIC)
