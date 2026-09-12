"""Acceptance tests for D5C1 Structural Signature RNG Sampler v0.1."""

import ast
from dataclasses import replace
import inspect
from pathlib import Path
from random import Random
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.structural_signature import (
    StructuralSignature,
    StructuralSignatureWeightSpec,
)
from anime_pref.sampling.config import load_sampler_config
import anime_pref.sampling.structural_signature as policy_module
from anime_pref.sampling.structural_signature import (
    load_structural_pattern_selection_policy,
    signature_probabilities,
    structural_pattern_selection_policy_sha256,
)
import anime_pref.sampling.structural_signature_sampler as sampler_module
from anime_pref.sampling.structural_signature_sampler import (
    sample_structural_signature,
)

SAMPLER_PATH = PROJECT_ROOT / "tests/fixtures/semantic_sampler.synthetic.v0.1.json"
POLICY_PATH = (
    PROJECT_ROOT
    / "tests/fixtures/structural_pattern_policy.synthetic.v0.1.json"
)


class CountingRandom:
    """Deterministic test double that exposes exact draw consumption."""

    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


def rehash(policy, entries=None, **changes):
    """Rebuild a valid policy identity after test-only content mutation."""
    if entries is not None:
        changes["signature_entries"] = tuple(
            sorted(entries, key=policy_module._entry_sort_key)
        )
    provisional = replace(policy, policy_hash="", **changes)
    return replace(
        provisional,
        policy_hash=structural_pattern_selection_policy_sha256(provisional),
    )


class SignatureSamplerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_sampler_config(SAMPLER_PATH)
        cls.policy = load_structural_pattern_selection_policy(POLICY_PATH)
        cls.multi_plan = FamilyComplexityPlan("single_constraint", "1")


class OperationalPipelineTests(SignatureSamplerTestCase):
    def test_public_entrypoint_binds_before_probability_lookup(self):
        events = []
        real_binding = sampler_module.validate_structural_pattern_selection_policy
        real_probabilities = sampler_module.signature_probabilities

        def bind(*args):
            events.append("binding")
            return real_binding(*args)

        def probabilities(*args):
            events.append("probabilities")
            return real_probabilities(*args)

        with patch.object(
            sampler_module,
            "validate_structural_pattern_selection_policy",
            side_effect=bind,
        ), patch.object(
            sampler_module,
            "signature_probabilities",
            side_effect=probabilities,
        ):
            sample_structural_signature(
                self.policy,
                self.config,
                self.multi_plan,
                CountingRandom([0.1]),
            )
        self.assertEqual(events, ["binding", "probabilities"])

    def test_candidate_mapping_and_order_come_directly_from_d5a(self):
        expected = signature_probabilities(self.policy, self.multi_plan)
        captured = {}

        def choose(choices, probabilities, rng):
            captured["choices"] = choices
            captured["probabilities"] = probabilities
            return choices[0]

        with patch.object(sampler_module, "_weighted_choice", side_effect=choose):
            selected = sample_structural_signature(
                self.policy,
                self.config,
                self.multi_plan,
                CountingRandom([]),
            )
        self.assertEqual(captured["choices"], tuple(expected))
        self.assertEqual(captured["probabilities"], expected)
        self.assertEqual(selected, next(iter(expected)))

    def test_multicandidate_context_consumes_exactly_one_draw(self):
        rng = CountingRandom([0.2, 0.9])
        result = sample_structural_signature(
            self.policy,
            self.config,
            self.multi_plan,
            rng,
        )
        self.assertEqual(result, StructuralSignature(("genre_set",)))
        self.assertEqual(rng.call_count, 1)

    def test_singleton_context_consumes_zero_draws(self):
        rng = CountingRandom([])
        result = sample_structural_signature(
            self.policy,
            self.config,
            FamilyComplexityPlan("same_field_logic", "2"),
            rng,
        )
        self.assertEqual(result, StructuralSignature(("genre_set",)))
        self.assertEqual(rng.call_count, 0)

    def test_reference_only_returns_reference_with_zero_draws(self):
        rng = CountingRandom([])
        result = sample_structural_signature(
            self.policy,
            self.config,
            FamilyComplexityPlan("reference_only", 0),
            rng,
        )
        self.assertEqual(result, StructuralSignature(("reference",)))
        self.assertEqual(rng.call_count, 0)

    def test_probability_intervals_use_half_open_existing_semantics(self):
        examples = (
            (0.0, ("genre_set",)),
            (0.499999999, ("genre_set",)),
            (0.5, ("year_range",)),
            (5 / 6 - 1e-12, ("year_range",)),
            (5 / 6, ("format_any",)),
            (0.999999999, ("format_any",)),
        )
        for draw, expected in examples:
            rng = CountingRandom([draw])
            with self.subTest(draw=draw):
                self.assertEqual(
                    sample_structural_signature(
                        self.policy,
                        self.config,
                        self.multi_plan,
                        rng,
                    ),
                    StructuralSignature(expected),
                )
                self.assertEqual(rng.call_count, 1)

    def test_same_seed_reproduces_selection_and_rng_advancement(self):
        left = Random(3817)
        right = Random(3817)
        left_result = sample_structural_signature(
            self.policy, self.config, self.multi_plan, left
        )
        right_result = sample_structural_signature(
            self.policy, self.config, self.multi_plan, right
        )
        self.assertEqual(left_result, right_result)
        self.assertEqual(left.getstate(), right.getstate())

    def test_exactly_one_rng_state_step_for_multicandidate_context(self):
        actual = Random(90210)
        expected = Random(90210)
        sample_structural_signature(
            self.policy, self.config, self.multi_plan, actual
        )
        expected.random()
        self.assertEqual(actual.getstate(), expected.getstate())

    def test_binding_itself_consumes_no_rng(self):
        rng = CountingRandom([])
        with patch.object(
            sampler_module,
            "signature_probabilities",
            side_effect=RuntimeError("stop after binding"),
        ):
            with self.assertRaises(RuntimeError):
                sample_structural_signature(
                    self.policy,
                    self.config,
                    self.multi_plan,
                    rng,
                )
        self.assertEqual(rng.call_count, 0)


class FailureBeforeDrawTests(SignatureSamplerTestCase):
    def assert_fails_without_draw(self, policy, config, plan, rng=None):
        rng = CountingRandom([0.1]) if rng is None else rng
        with self.assertRaises((ValueError, TypeError)):
            sample_structural_signature(policy, config, plan, rng)
        self.assertEqual(getattr(rng, "call_count", 0), 0)

    def test_bad_policy_hash_fails_before_draw(self):
        self.assert_fails_without_draw(
            replace(self.policy, policy_hash="0" * 64),
            self.config,
            self.multi_plan,
        )

    def test_sampler_version_mismatch_fails_before_draw(self):
        mismatch = rehash(self.policy, sampler_version="other-sampler-v0.1")
        self.assert_fails_without_draw(mismatch, self.config, self.multi_plan)

    def test_invalid_family_plan_fails_before_draw(self):
        self.assert_fails_without_draw(
            self.policy,
            self.config,
            FamilyComplexityPlan("cross_field_composition", "1"),
        )

    def test_invalid_rng_interface_fails_without_draw(self):
        class InvalidRng:
            random = 1
            call_count = 0

        self.assert_fails_without_draw(
            self.policy,
            self.config,
            self.multi_plan,
            InvalidRng(),
        )

    def test_d4_invalid_configured_signature_fails_before_draw(self):
        entries = [
            entry
            for entry in self.policy.signature_entries
            if not (
                entry.semantic_family == "cross_field_composition"
                and entry.complexity_bucket == "2"
            )
        ]
        entries.append(
            StructuralSignatureWeightSpec(
                "cross_field_composition",
                "2",
                ("format_any", "reference"),
                1,
            )
        )
        malformed = rehash(self.policy, entries=entries)
        self.assert_fails_without_draw(malformed, self.config, self.multi_plan)

    def test_uncovered_b_context_fails_before_draw(self):
        entries = tuple(
            entry
            for entry in self.policy.signature_entries
            if not (
                entry.semantic_family == "reference_only"
                and entry.complexity_bucket == 0
            )
        )
        incomplete = rehash(self.policy, entries=entries)
        self.assert_fails_without_draw(incomplete, self.config, self.multi_plan)


class InvarianceTests(SignatureSamplerTestCase):
    def test_scale_equivalent_weights_select_same_but_hashes_differ(self):
        entries = tuple(
            replace(entry, weight=entry.weight * 10)
            if entry.semantic_family == "single_constraint"
            and entry.complexity_bucket == "1"
            else entry
            for entry in self.policy.signature_entries
        )
        scaled = rehash(self.policy, entries=entries)
        self.assertNotEqual(self.policy.policy_hash, scaled.policy_hash)
        for draw in (0.1, 0.6, 0.9):
            with self.subTest(draw=draw):
                baseline_rng = CountingRandom([draw])
                scaled_rng = CountingRandom([draw])
                baseline = sample_structural_signature(
                    self.policy, self.config, self.multi_plan, baseline_rng
                )
                selected = sample_structural_signature(
                    scaled, self.config, self.multi_plan, scaled_rng
                )
                self.assertEqual(baseline, selected)
                self.assertEqual(baseline_rng.call_count, scaled_rng.call_count)

    def test_other_context_weights_do_not_change_current_selection(self):
        entries = tuple(
            replace(entry, weight=entry.weight * 100)
            if entry.semantic_family == "cross_field_composition"
            else entry
            for entry in self.policy.signature_entries
        )
        changed = rehash(self.policy, entries=entries)
        left = CountingRandom([0.7])
        right = CountingRandom([0.7])
        self.assertEqual(
            sample_structural_signature(
                self.policy, self.config, self.multi_plan, left
            ),
            sample_structural_signature(
                changed, self.config, self.multi_plan, right
            ),
        )
        self.assertEqual(left.call_count, right.call_count)


class PhaseBoundaryTests(unittest.TestCase):
    def test_output_is_structural_signature_without_wrapper(self):
        config = load_sampler_config(SAMPLER_PATH)
        policy = load_structural_pattern_selection_policy(POLICY_PATH)
        result = sample_structural_signature(
            policy,
            config,
            FamilyComplexityPlan("single_constraint", "1"),
            CountingRandom([0.1]),
        )
        self.assertIsInstance(result, StructuralSignature)

    def test_module_has_no_mechanics_domain_or_downstream_dependencies(self):
        source = inspect.getsource(sampler_module)
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        forbidden = {
            "anime_pref.sampling.mechanics_probability",
            "anime_pref.data.query_builder",
            "anime_pref.schemas.taxonomy",
            "anime_pref.schemas.preference_query",
            "anime_pref.schemas.dataset_record",
        }
        self.assertTrue(forbidden.isdisjoint(imported))
        self.assertNotIn("mechanics_pattern_probabilities", source)
        self.assertNotIn("while ", source)
        self.assertNotIn("Random(", source)


if __name__ == "__main__":
    unittest.main()
