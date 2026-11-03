"""List projections deliberately exclude large source documents and job reports."""
from types import SimpleNamespace
from .models import Repository, Job


def library_rows(query):
    names = ('id', 'full_name', 'description', 'language', 'stars', 'forks', 'favorite',
             'collected', 'tags', 'notes', 'study_status', 'archived', 'summary', 'fetched_at')
    metadata_keys = ('html_url', 'topics', 'license', 'created_at', 'homepage')
    columns = [getattr(Repository, name) for name in names]
    columns += [Repository.metadata_json[key].label('_meta_' + key) for key in metadata_keys]
    for row in query.with_entities(*columns):
        values = dict(row._mapping)
        metadata = {key: values.pop('_meta_' + key) for key in metadata_keys}
        yield SimpleNamespace(**values, metadata_json=metadata)


def job_rows(query):
    names = ('id', 'kind', 'status', 'stage', 'attempts', 'error', 'created_at', 'available_at')
    columns = [getattr(Job, name) for name in names]
    columns += [Job.payload['browser_runs'].as_integer().label('browser_runs'),
                Job.payload['provider'].as_string().label('provider')]
    for row in query.with_entities(*columns):
        yield SimpleNamespace(**dict(row._mapping))
