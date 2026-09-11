"""Regression tests for Semantic Sampler Config v0.1."""

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import load_domain_rules
from anime_pref.sampling.config import (
    load_sampler_config,
    validate_sampler_config,
    validate_sampler_config_against_domain,
)
from anime_pref.data.tag_subset import load_executable_tag_subset

SAMPLER_CONFIG_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "semantic_sampler.synthetic.v0.1.json"
)
RULES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "domain_rules.synthetic.v0.1.json"
SUBSET_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "executable_tags.synthetic.v0.1.json"
)


class SemanticSamplerConfigTests(unittest.TestCase):
    def test_loads_complete_immutable_sampler_contract(self):
        config = load_sampler_config(SAMPLER_CONFIG_PATH)
        self.assertEqual(config.seed, 1729)
        self.assertEqual(config.constraint_count_weights.weights["1"], 35)
        self.assertEqual(set(config.operator_cardinality.any_of), {2, 3})
        self.assertIsNone(validate_sampler_config(config))

        with self.assertRaises(TypeError):
            config.family_weights.weights["single_constraint"] = 999

    def test_rejects_unknown_keys_invalid_weights_and_bad_cardinality(self):
        import json

        source = json.loads(SAMPLER_CONFIG_PATH.read_text(encoding="utf-8"))
        cases = []

        unknown = dict(source)
        unknown["unknown_policy"] = {}
        cases.append(unknown)

        zero_weight = json.loads(json.dumps(source))
        zero_weight["operator_weights"]["any_of"] = 0
        cases.append(zero_weight)

        bad_cardinality = json.loads(json.dumps(source))
        bad_cardinality["operator_cardinality"]["any_of"]["4"] = 1
        cases.append(bad_cardinality)

        duplicate_numeric = json.loads(json.dumps(source))
        duplicate_numeric["numeric_sampling"]["year"]["long_tail_values"].append(2000)
        cases.append(duplicate_numeric)

        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, invalid in enumerate(cases):
                with self.subTest(case=index):
                    path = Path(temporary_directory) / f"invalid-{index}.json"
                    path.write_text(json.dumps(invalid), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_sampler_config(path)

    def test_rejects_directly_constructed_invalid_standalone_policies(self):
        config = load_sampler_config(SAMPLER_CONFIG_PATH)

        def replace_weight(table, key, value):
            weights = dict(table.weights)
            weights[key] = value
            return replace(table, weights=weights)

        cases = (
            (
                "version_whitespace",
                replace(config, sampler_version=" bad-version"),
            ),
            ("bool_seed", replace(config, seed=True)),
            (
                "nan_weight",
                replace(
                    config,
                    family_weights=replace_weight(
                        config.family_weights,
                        "single_constraint",
                        float("nan"),
                    ),
                ),
            ),
            (
                "zero_coverage",
                replace(
                    config,
                    genre_sampling=replace(
                        config.genre_sampling,
                        minimum_coverage_per_value=0,
                    ),
                ),
            ),
            (
                "priority_key_whitespace",
                replace(
                    config,
                    tag_sampling=replace(
                        config.tag_sampling,
                        priority_weights={" Female Harem": 1.0},
                    ),
                ),
            ),
            (
                "unknown_tier",
                replace(
                    config,
                    tag_sampling=replace(
                        config.tag_sampling,
                        value_tiers={"Female Harem": "unknown"},
                    ),
                ),
            ),
            (
                "numeric_not_sorted",
                replace(
                    config,
                    year_sampling=replace(
                        config.year_sampling,
                        common_values=(2020, 2000),
                    ),
                ),
            ),
            (
                "numeric_duplicate",
                replace(
                    config,
                    year_sampling=replace(
                        config.year_sampling,
                        common_values=(2000, 2000),
                    ),
                ),
            ),
            (
                "numeric_bool",
                replace(
                    config,
                    year_sampling=replace(
                        config.year_sampling,
                        common_values=(True,),
                    ),
                ),
            ),
            (
                "numeric_cross_pool_overlap",
                replace(
                    config,
                    year_sampling=replace(
                        config.year_sampling,
                        long_tail_values=(2000,),
                    ),
                ),
            ),
            (
                "tolerance_above_one",
                replace(
                    config,
                    audit_tolerances=replace(
                        config.audit_tolerances,
                        maximum_signature_share=1.1,
                    ),
                ),
            ),
        )

        for case, invalid in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    validate_sampler_config(invalid)
    def test_binds_value_and_numeric_policies_to_actual_domain(self):
        config = load_sampler_config(SAMPLER_CONFIG_PATH)
        rules = load_domain_rules(RULES_PATH)
        subset = load_executable_tag_subset(SUBSET_PATH)
        self.assertIsNone(
            validate_sampler_config_against_domain(config, rules, subset)
        )

        bad_genre = replace(
            config.genre_sampling,
            priority_weights={"Not Active": 1.0},
        )
        with self.assertRaises(ValueError):
            validate_sampler_config_against_domain(
                replace(config, genre_sampling=bad_genre),
                rules,
                subset,
            )

        bad_year = replace(
            config.year_sampling,
            long_tail_values=(1899,),
        )
        with self.assertRaises(ValueError):
            validate_sampler_config_against_domain(
                replace(config, year_sampling=bad_year),
                rules,
                subset,
            )

    def test_rejects_inactive_tag_sampling_values(self):
        config = load_sampler_config(SAMPLER_CONFIG_PATH)
        rules = load_domain_rules(RULES_PATH)
        subset = load_executable_tag_subset(SUBSET_PATH)

        cases = (
            replace(
                config,
                tag_sampling=replace(
                    config.tag_sampling,
                    priority_weights={"Ensemble Cast": 1.0},
                ),
            ),
            replace(
                config,
                tag_sampling=replace(
                    config.tag_sampling,
                    value_tiers={"Ensemble Cast": "core"},
                ),
            ),
        )

        for invalid in cases:
            with self.subTest(config=invalid):
                with self.assertRaises(ValueError):
                    validate_sampler_config_against_domain(
                        invalid,
                        rules,
                        subset,
                    )

    def test_rejects_missing_normalization_group_and_episode_bound(self):
        import json

        config = load_sampler_config(SAMPLER_CONFIG_PATH)
        subset = load_executable_tag_subset(SUBSET_PATH)
        source = json.loads(RULES_PATH.read_text(encoding="utf-8"))

        without_groups = json.loads(json.dumps(source))
        without_groups["tag_groups"] = {}

        bounded_episodes = json.loads(json.dumps(source))
        bounded_episodes["numeric_rules"]["episodes"]["maximum"] = 100

        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = []
            for index, document in enumerate((without_groups, bounded_episodes)):
                path = Path(temporary_directory) / f"rules-{index}.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                paths.append(path)

            for path in paths:
                with self.subTest(path=path.name):
                    rules = load_domain_rules(path)
                    with self.assertRaises(ValueError):
                        validate_sampler_config_against_domain(
                            config,
                            rules,
                            subset,
                        )

if __name__ == "__main__":
    unittest.main()
