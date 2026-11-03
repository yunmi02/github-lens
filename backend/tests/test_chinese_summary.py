import json
from app.config import settings
from app.summary import (apply_verified_summary, build_summary, needs_chinese_summary,
                         quote_from_original, repair_overview_from_claims,
                         summary_health, verify_claim)

URL = 'https://github.com/owner/tool'


def claim(text='可用于文档批量识别', quote='Extract text from images', source=URL):
    return {'text': text, 'quote': quote, 'source': source}


def test_quote_normalization_keeps_the_actual_original_span_and_rejects_changed_words():
    original = 'Before: Extract\n  text&nbsp;from\timages. After.'
    assert quote_from_original('Extract text from images', original) == 'Extract\n  text&nbsp;from\timages'
    assert quote_from_original('Extract faces from images', original) is None
    assert quote_from_original('a  b    c', 'a b c') is None
    marked = '只需提供一个视频 <b>主题</b> 或 <b>关键词</b> ，就可以全自动生成视频文案。'
    quoted = '只需提供一个视频 主题 或 关键词 ，就可以全自动生成视频文案。'
    assert quote_from_original(quoted, marked) == marked
    assert quote_from_original('完整的 MVC架构，代码 结构清晰，支持 API 和 Web界面',
        '完整的 **MVC架构**，代码 **结构清晰**，支持 `API` 和 `Web界面`') == '完整的 **MVC架构**，代码 **结构清晰**，支持 `API` 和 `Web界面'
    assert quote_from_original('variable snakecaseidentifier', 'variable snake_case_identifier') is None


def test_claims_require_chinese_and_actual_source_evidence():
    originals = {'readme': 'Extract text from images'}
    assert verify_claim(claim(source='readme'), originals, {'readme': URL})['source'] == URL
    assert verify_claim(claim(source='README'), originals, {'readme': URL})['source'] == URL
    assert verify_claim(claim(text='Extract text from images', source='readme'), originals, {'readme': URL}) is None
    assert verify_claim(claim(source='https://unprovided.example/docs'), originals) is None
    assert verify_claim(claim(quote='Make videos from prompts', source='readme'), originals, {'readme': URL}) is None


def test_all_rejected_model_output_cannot_be_labelled_as_a_success():
    result = apply_verified_summary({'mode': 'source', 'overview': claim(text='An English description'), 'functions': []},
        {'overview': claim(text='English output'), 'functions': [claim(quote='Invented feature quote')]}, {URL: 'Extract text from images'})
    assert result['mode'] == 'source'
    assert result['verified_count'] == 0 and needs_chinese_summary(result)
    assert result['generation_status'] == 'invalid' and result['generation_retryable']


def test_existing_chinese_functions_can_supply_an_explicitly_labelled_overview_without_ai():
    existing = {'mode': 'browser', 'overview': claim(text='A document toolkit'),
                'functions': [claim()], 'use_cases': [claim(text='适合整理扫描文档')],
                'requirements': [], 'innovations': []}
    fixed = repair_overview_from_claims(existing)
    assert fixed['overview']['text'] == '功能概述：可用于文档批量识别'
    assert fixed['overview']['quote'] == existing['functions'][0]['quote']
    assert fixed['overview_from_functions']
    assert summary_health(fixed)['complete']
    assert existing['overview']['text'] == 'A document toolkit'
    english = {'overview': claim(text='中文 ' + 'English paragraph ' * 30), 'functions': [claim()]}
    assert not summary_health(english)['overview_zh']


def test_generation_accepts_fenced_json_and_trailing_annotations_and_preserves_quotes(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_base_url', 'https://api.deepseek.com')
    monkeypatch.setattr(settings, 'ai_api_key', 'test')
    monkeypatch.setattr(settings, 'ai_model', 'test')
    generated = {'overview': claim(text='这是一个文档文字识别工具', source='readme'),
                 'functions': [claim(source='readme')],
                 'use_cases': [claim(text='适合整理扫描文档', source='readme')]}
    monkeypatch.setattr('app.research.post_json', lambda *args: {'choices': [{'message': {
        'content': '```json\n\n' + json.dumps(generated) + '\n```\nSource annotations'}}]})
    result = build_summary({'full_name': 'owner/tool', 'description': 'A document toolkit', 'html_url': URL},
                           'Extract\n  text from images', URL + '#readme')
    assert result['mode'] == 'ai' and result['health']['complete']
    assert result['overview']['quote'] == 'Extract\n  text from images'
    assert result['overview']['source'] == URL + '#readme'


def test_verified_regeneration_preserves_existing_chinese_fields_when_new_output_omits_them():
    original = {URL: 'Extract text from images'}
    previous = {'mode': 'browser', 'functions': [claim()], 'use_cases': [claim(text='适合整理扫描文档')]}
    updated = apply_verified_summary(previous, {'overview': claim(text='这是文档识别项目')}, original, mode='browser')
    assert updated['functions'] == previous['functions']
    assert updated['use_cases'] == previous['use_cases']
    assert updated['health']['complete']


def test_generation_failure_reports_retryable_status_instead_of_a_completed_translation(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_base_url', 'https://api.deepseek.com')
    monkeypatch.setattr(settings, 'ai_api_key', 'test')
    monkeypatch.setattr(settings, 'ai_model', 'test')
    monkeypatch.setattr('app.research.post_json', lambda *args: {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]})
    result = build_summary({'description': 'A document toolkit', 'html_url': URL}, 'Extract text from images', URL + '#readme')
    assert result['mode'] == 'source' and not result['health']['complete']
    assert result['generation_status'] == 'failed'
    assert result['generation_error'] == 'invalid_response' and result['generation_retryable']


def test_rendered_readme_quotes_and_uppercase_aliases_are_accepted_without_changing_evidence(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_base_url', 'https://api.deepseek.com')
    monkeypatch.setattr(settings, 'ai_api_key', 'test')
    monkeypatch.setattr(settings, 'ai_model', 'test')
    readme = '只需提供一个视频 <b>主题</b> 或 <b>关键词</b> ，就可以全自动生成视频文案。'
    quote = '只需提供一个视频 主题 或 关键词 ，就可以全自动生成视频文案。'
    generated = {'overview': '一个视频生成工具',
                 'functions': [claim(text='根据主题或关键词自动生成视频文案', quote=quote, source='README')],
                 'use_cases': [claim(text='适合需要主题短视频文案的用户', quote=quote, source='README')]}
    monkeypatch.setattr('app.research.post_json', lambda *args: {'choices': [{'message': {'content': json.dumps(generated)}}]})
    result = build_summary({'description': 'AI video generator', 'html_url': URL}, readme, URL + '#readme')
    assert result['generation_status'] == 'complete' and result['health']['complete']
    assert result['overview_from_functions']
    assert result['functions'][0]['source'] == URL + '#readme'
    assert result['functions'][0]['quote'] == readme
