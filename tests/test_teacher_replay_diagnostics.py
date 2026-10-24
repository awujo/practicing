"""Independent limits on source-label diagnostics; no historical acceptance fixtures."""
from reports.replay_teacher_examples_v2 import plan_checkpoints


def report(groups=(), *, prices=(1.1, 1.0, 1.3), coverage='COMPLETE'):
    return {'source_plan':dict(tf='H2',trigger='breakout',**dict(zip(('entry','stop','target'),prices))),
            'plan_groups':list(groups),'coverage':{'timeframes':{'H2':{'status':coverage}}}}


def group(ident, entry, stop, target):
    return dict(representative_setup_id=ident,model='confirmation_bo',
                prices=dict(entry=str(entry),stop=str(stop),target=str(target)))


def test_plan_labels_cannot_be_combined_across_different_causal_plans():
    source=report((group('entry_only',1.1,.9,1.4),group('stop_only',1.2,1.0,1.4),
                   group('target_only',1.2,.9,1.3)))
    result=plan_checkpoints(source)
    assert result['entry_label_equal_groups']==1
    assert result['exact_numeric_plan'] is False
    assert result['exact_plan_setup_ids']==[]
    assert result['status']=='NO_EXACT_NUMERIC_PLAN_ON_ALTERNATE_FEED'
    source['plan_groups'].append(group('complete_plan',1.1,1.0,1.3))
    whole=plan_checkpoints(source)
    assert whole['exact_plan_setup_ids']==['complete_plan']
    assert whole['status']=='EXACT_NUMERIC_PLAN_PRESENT_NOT_TRADE_ACCEPTANCE'
    assert whole['source_route_identity']=='NAMED_FAMILY_ONLY_CANDLE_IDENTITY_UNRESOLVED'


def test_context_only_source_with_null_labels_cannot_be_numeric_match():
    result=plan_checkpoints(report((group('candidate',1.1,1.0,1.3),),prices=(None,None,None)))
    assert result['status']=='CONTEXT_ONLY_SOURCE_LABELS'
    assert result['exact_numeric_plan'] is False
    assert result['exact_plan_setup_ids']==[]


def test_unsupported_entry_resolution_never_matches_even_identical_labels():
    result=plan_checkpoints(report((group('identical',1.1,1.0,1.3),),coverage='UNRESOLVED_RESOLUTION'))
    assert result['status']=='ENTRY_RESOLUTION_UNAVAILABLE'
    assert result['exact_numeric_plan'] is False
    assert result['source_route_identity']=='UNRESOLVED'
