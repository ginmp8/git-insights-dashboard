"""Headless UI contract: annual table reads persisted full coverage, no implicit GH calls."""
import importlib
from contextlib import nullcontext
import sys
import types
import subprocess

from gitinsights.incremental import MetricsStore, sync_repository


def test_annual_ui_is_local_and_full_coverage(monkeypatch, tmp_path):
    repo=tmp_path/'repo'
    repo.mkdir()
    def git(*args):
        subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
    git('init','-b','main')
    git('config','user.name','Alice')
    git('config','user.email','alice@example.com')
    (repo/'hello.py').write_text('print("hello")\n')
    git('add','-A')
    git('commit','-m','first')
    store_path=tmp_path/'metrics.db'
    with MetricsStore(store_path) as store:
        sync_repository(store,'r',repo,'refs/heads/main')

    fake=types.ModuleType('streamlit')
    fake.session_state={}
    events=[]
    def log(name):
        def call(*a,**kw):
            events.append((name,a,kw))
        return call
    for attr in ('subheader','caption','metric','markdown','warning','success','error',
                 'info','dataframe','download_button','line_chart','write'):
        setattr(fake,attr,log(attr))
    fake.number_input=lambda *a,**kw: 2026
    fake.selectbox=lambda label,options,**kw: options[0]
    fake.button=lambda *a,**kw: False
    fake.text_input=lambda *a,**kw: ''
    fake.form_submit_button=lambda *a,**kw: False
    fake.spinner=fake.expander=fake.form=lambda *a,**kw: nullcontext()
    fake.columns=lambda n:[types.SimpleNamespace(metric=log('metric')) for _ in range(n)]
    fake.progress=lambda *a,**kw: types.SimpleNamespace(progress=log('progress'))
    monkeypatch.setitem(sys.modules,'streamlit',fake)
    sys.modules.pop('gitinsights.ui_annual',None)
    ui=importlib.import_module('gitinsights.ui_annual')
    monkeypatch.setattr(ui,'list_pr_collaboration',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('Network request')))
    ui.render_annual({'id':'p','name':'Test'},[{'id':'r','name':'Repo','path':str(repo),'url':''}],store_path)
    assert any(name=='dataframe' for name,_,_ in events)
    assert any(name=='download_button' for name,_,_ in events)
    assert not any(name=='warning' for name,_,_ in events)
    sys.modules.pop('gitinsights.ui_annual',None)
