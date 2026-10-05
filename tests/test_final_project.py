"""Focused offline acceptance for the final data and recommendation chain."""
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import shutil
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from anime_pref.data.catalog import catalog_jsonl,load_catalog
from anime_pref.data.query_builder import build_query,load_domain_rules,dumps_query
from anime_pref.data.query_validation import canonicalize_query
from anime_pref.data.domain_validation import validate_query_domain
from anime_pref.data.rules_identity import validate_executable_rules_identity
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.data.final_dataset import reviewed_patterns,realize_final_text,generate_final_dataset
from anime_pref.schemas.preference_query import SemanticSpec,SetConstraintSpec,RangeConstraintSpec
from anime_pref.sampling.structural_pattern import validate_structural_pattern_plan
from anime_pref.retrieval.executor import execute_query,rank_candidates,resolve_reference
from anime_pref.recommendation import RecommendationService
from anime_pref.training.final_training import load_final_config,load_final_records


def anime(id,genres,tags=(),year=2020,episodes=12,fmt='TV',status='FINISHED',popularity=100,score=80):
    return {'id':id,'title':{'romaji':f'Title {id}','english':None,'native':None},
        'genres':list(genres),'tags':[{'name':n,'rank':r} for n,r in tags],
        'year':year,'episodes':episodes,'format':fmt,'status':status,
        'popularity':popularity,'averageScore':score,'isAdult':False}


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=load_domain_rules(ROOT/'tests/fixtures/domain_rules.synthetic.v0.1.json')
        cls.catalog=[anime(1,('Mystery','Sci-Fi'),(('Female Harem',80),)),
                     anime(2,('Mystery',),year=2010,episodes=24),
                     anime(3,('Sci-Fi',),year=None,episodes=None,fmt='MOVIE')]
    def query(self,**kw):return build_query(SemanticSpec(**kw),self.rules)
    def ids(self,q):return [r['id'] for r in execute_query(q,self.catalog)]
    def test_genre_all_any_none(self):
        C=SetConstraintSpec
        self.assertEqual(self.ids(self.query(genres=C(all_of=('Mystery','Sci-Fi')))),[1])
        self.assertEqual(self.ids(self.query(genres=C(any_of=('Mystery','Sci-Fi')))),[1,2,3])
        self.assertEqual(self.ids(self.query(genres=C(none_of=('Mystery',)))),[3])
    def test_tag_all_any_none_and_rank_policy(self):
        C=SetConstraintSpec
        self.assertEqual(self.ids(self.query(tags=C(all_of=('Female Harem',)))),[1])
        self.assertEqual(self.ids(self.query(tags=C(any_of=('Female Harem','Male Harem')))),[1])
        self.assertEqual(self.ids(self.query(tags=C(none_of=('Female Harem',)))),[2,3])
        weak=anime(4,(),(('Female Harem',10),))
        self.assertEqual(execute_query(self.query(tags=C(all_of=('Female Harem',))),[weak]),[])
        self.assertEqual(execute_query(self.query(tags=C(none_of=('Female Harem',))),[weak]),[])
    def test_inclusive_numeric_ranges_and_unknown_metadata(self):
        q=self.query(year=RangeConstraintSpec(min=2010,max=2020),episodes=RangeConstraintSpec(max=24))
        self.assertEqual(self.ids(q),[1,2])
        self.assertEqual(self.ids(self.query(episodes=RangeConstraintSpec(min=13))),[2])
    def test_format_status_or_and_combination(self):
        self.assertEqual(self.ids(self.query(formats=('TV','MOVIE'),status=('FINISHED','RELEASING'))),[1,2,3])
        self.assertEqual(self.ids(self.query(formats=('TV',),tags=SetConstraintSpec(none_of=('Female Harem',)))),[2])
    def test_reference_never_changes_filter(self):
        q=self.query(reference_titles=('Title 1',))
        self.assertEqual(self.ids(q),[1,2,3])
        self.assertEqual(resolve_reference('title 1',self.catalog)['id'],1)
        self.assertIsNone(resolve_reference('missing',self.catalog))
        self.assertIsNone(resolve_reference('Title 1',self.catalog+[self.catalog[0]]))
    def test_ranking_stable_and_reference_similarity_bonus(self):
        q=self.query(reference_titles=('Title 1',))
        first=rank_candidates(q,self.catalog,self.catalog)
        second=rank_candidates(q,list(reversed(self.catalog)),self.catalog)
        self.assertEqual([r['id'] for r in first],[r['id'] for r in second])
        self.assertGreater(first[0]['score_components']['reference_similarity'],0)
    def test_catalog_loading_and_hash_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'catalog.jsonl';manifest=Path(d)/'manifest.json'
            data=catalog_jsonl(reversed(self.catalog));path.write_text(data,encoding='utf-8',newline='')
            manifest.write_text(json.dumps({'catalog_sha256':sha256(data.encode()).hexdigest(),'record_count':3}))
            self.assertEqual(len(load_catalog(path,manifest)),3)
            manifest.write_text(json.dumps({'catalog_sha256':'0'*64,'record_count':3}))
            with self.assertRaises(ValueError):load_catalog(path,manifest)
    def test_mock_parser_full_chain_and_failure_fallbacks(self):
        class Parser:
            def __init__(self,value):self.value=value
            def generate_batch(self,texts):
                self.seen=tuple(texts)
                return (self.value,)
        good=dumps_query(self.query(genres=SetConstraintSpec(all_of=('Mystery',))))
        result=RecommendationService(Parser(good),self.rules,self.catalog).recommend_anime('想看悬疑',2)
        self.assertEqual(result['status'],'ok');self.assertEqual(result['candidate_count'],2)
        parser=Parser(good)
        padded=RecommendationService(parser,self.rules,self.catalog).recommend_anime(' 想看悬疑 ',2)
        self.assertEqual(parser.seen,('想看悬疑',))
        self.assertEqual(padded['user_text'],' 想看悬疑 ')
        self.assertEqual(RecommendationService(Parser('```json\n{}\n```'),self.rules,self.catalog).recommend_anime('x')['status'],'parse_failed')
        bad=self.query();bad['hard_constraints']['status']=['TV']
        self.assertEqual(RecommendationService(Parser(json.dumps(bad)),self.rules,self.catalog).recommend_anime('x')['status'],'validation_failed')
        empty=dumps_query(self.query(year=RangeConstraintSpec(min=2099)))
        self.assertEqual(RecommendationService(Parser(empty),self.rules,self.catalog).recommend_anime('x')['status'],'no_matches')


class RealDataContractTests(unittest.TestCase):
    def test_dataset_regeneration_is_identical_from_real_snapshots(self):
        # A separate temporary root proves generation does not depend on time,
        # a live API, model outputs or accidentally reused final artifacts.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for relative in ('data/catalog/anilist_catalog_v0.1.jsonl','data/catalog/manifest.json',
                             'data/domain/taxonomy_v0.2/canonical.json','configs/e0_system_prompt.v0.2.txt',
                             'tests/fixtures/domain_rules.synthetic.v0.1.json',
                             'tests/fixtures/semantic_sampler.synthetic.v0.1.json'):
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,target)
            shutil.copytree(ROOT/'data/pilot',root/'data/pilot')
            generate_final_dataset(root)
            for split in ('train','validation','test','challenge'):
                name=f'data/final/{split}.v0.2.jsonl'
                self.assertEqual((root/name).read_bytes(),(ROOT/name).read_bytes())
    def test_real_domain_lineage_and_no_synthetic_identity(self):
        rules=load_domain_rules(ROOT/'configs/domain_rules.v0.2.json')
        subset=load_executable_tag_subset(ROOT/'data/domain/subset_v0.2/executable_tags.json')
        validate_executable_rules_identity(rules,subset)
        self.assertNotIn('synthetic',rules.rules_version)
        self.assertTrue(50<=len(subset.tags)<=150)
        self.assertTrue(all(not t.is_adult and not t.is_general_spoiler for t in subset.tags))
    def test_real_catalog_size_and_manifest(self):
        rows=load_catalog(ROOT/'data/catalog/anilist_catalog_v0.1.jsonl',ROOT/'data/catalog/manifest.json')
        self.assertTrue(1000<=len(rows)<=3000)
        self.assertTrue(all(not r['isAdult'] for r in rows))
    def test_reviewed_patterns_and_realization_is_explicit(self):
        for pattern in reviewed_patterns():validate_structural_pattern_plan(pattern)
        spec=SemanticSpec(year=RangeConstraintSpec(min=2015),formats=('TV',))
        text=realize_final_text(spec,0)
        self.assertIn('2015年及以后',text);self.assertNotIn('状态',text)
        self.assertIn('TV',text)
    def test_splits_and_challenge_have_zero_exact_overlap(self):
        data={s:[json.loads(l) for l in (ROOT/f'data/final/{s}.v0.2.jsonl').read_text(encoding='utf-8').splitlines()] for s in ('train','validation','test','challenge')}
        self.assertEqual({s:len(r) for s,r in data.items()},{'train':1200,'validation':150,'test':150,'challenge':40})
        for i,left in enumerate(data):
            for right in tuple(data)[i+1:]:
                self.assertFalse({r['user_text'] for r in data[left]}&{r['user_text'] for r in data[right]})
        rules=load_domain_rules(ROOT/'configs/domain_rules.v0.2.json')
        for rows in data.values():
            for row in rows:validate_query_domain(row['gold_query'],rules)
    def test_final_training_excludes_test_and_keeps_model_identity(self):
        config=load_final_config(ROOT/'configs/final_qlora.v0.2.json')
        self.assertEqual(len(load_final_records(ROOT,'train',config)),1200)
        for split in ('test','challenge'):
            with self.assertRaises(ValueError):load_final_records(ROOT,split,config)
        self.assertEqual(config.num_train_epochs,1)

if __name__=='__main__':unittest.main()
