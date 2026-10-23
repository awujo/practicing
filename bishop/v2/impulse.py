"""Optional, declared body/prior-ATR assessment; not a teaching constant.

The study establishes scope-specific impulsive disrespect, but no universal
number. None leaves it UNKNOWN. Enabling this numerical hypothesis does not
qualify a source example or gate raw breaks in unrelated source routes.
"""
from dataclasses import replace
from decimal import Decimal
from .types import Event, stable_id


def assess(structure, bars, policy):
    if policy.impulse_atr_fraction is None:
        return structure
    bars=tuple(bars); index={b.id:i for i,b in enumerate(bars)}
    true_ranges=[]; count=0
    for i,b in enumerate(bars):
        if i==0 or bars[i-1].segment_id!=b.segment_id:
            count=0
        previous=bars[i-1].close_ticks if count else b.open_ticks
        tr=max(b.high_ticks-b.low_ticks,abs(b.high_ticks-previous),abs(b.low_ticks-previous))
        true_ranges.append(tr); count+=1
    assessments=[]
    for event in structure.events:
        if event.kind!='LEVEL_ROLE_CHANGE' or not event.bar_ids: continue
        i=index.get(event.bar_ids[-1])
        if i is None: continue
        bar=bars[i]; n=policy.impulse_atr_period
        prior=bars[max(0,i-n):i]
        dependency=bars[i-n-1:i-n] if i>n and bars[i-n-1].segment_id==bar.segment_id else ()
        enough=len(prior)==n and all(b.segment_id==bar.segment_id and b.available_at<=event.available_at for b in (*dependency,*prior))
        atr=Decimal(sum(true_ranges[i-n:i]))/n if enough else None
        body=abs(bar.close_ticks-bar.open_ticks)
        qualification='UNKNOWN' if atr is None or atr<=0 else ('IMPULSE_CONFIRMED' if Decimal(body)>=atr*policy.impulse_atr_fraction else 'NOT_CONFIRMED')
        assessments.append(Event(id=stable_id('impulse',event.id,policy.id),kind='IMPULSE_ASSESSMENT',instrument=event.instrument,tf=event.tf,clock=event.clock,side=event.side,reference_id=event.id,bar_ids=tuple(b.id for b in (*dependency,*prior,bar)),evidence_ids=(event.id,),policy_id=policy.id,evidence_status='UNKNOWN' if qualification=='UNKNOWN' else 'KNOWN',details={'qualification':qualification,'method':'body_vs_prior_atr_v1_OUR_CHOICE','atr_ticks':atr,'body_ticks':body,'fraction':policy.impulse_atr_fraction,'period':n}))
    return replace(structure,events=tuple(sorted((*structure.events,*assessments),key=lambda e:(e.available_at,e.id))))
