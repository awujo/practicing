"""Observation-gap propagation. Missing prices are not a market reversal."""
from dataclasses import replace
from .types import Clock, Event, stable_id


def gaps_from_base(bars, policy):
    return tuple(Event(id=stable_id('base_gap',left.id,right.id,policy.id),kind='DATA_GAP',
        instrument=right.instrument,tf=right.tf,
        clock=Clock(left.end,right.start,max(left.available_at,right.available_at)),bar_ids=(left.id,right.id),
        policy_id=policy.id,evidence_status='UNKNOWN',
        details={'reason':'MISSING_OBSERVATIONS','previous_segment':left.segment_id,'next_segment':right.segment_id})
        for left,right in zip(bars,bars[1:]) if left.segment_id!=right.segment_id)


def invalidate_levels(result, gaps, policy):
    """A base gap invalidates old inference immediately when observed.

    Waiting for the first subsequent weekly candle would leave old weekly
    levels usable through a missing-hour interval. Occurrence and receipt
    clocks remain separate; a future gap never rewrites an earlier query.
    """
    if not gaps:return result
    additions=[]
    for gap in gaps:
        for level in result.levels:
            if level.formed_at>gap.clock.occurred_from:continue
            available=max(gap.available_at,level.available_at)
            additions.append(Event(id=stable_id('gap_level_unavailable',gap.id,level.id,policy.id),
                kind='LEVEL_UNAVAILABLE',instrument=level.instrument,tf=level.tf,
                clock=Clock(gap.clock.occurred_from,gap.clock.occurred_to,available),
                side=level.side,reference_id=level.id,bar_ids=gap.bar_ids,
                evidence_ids=(gap.id,level.id),policy_id=policy.id,evidence_status='UNKNOWN',
                details={'reason':'BASE_DATA_GAP','market_reversal':False}))
    return replace(result,events=tuple(sorted((*result.events,*additions),key=lambda e:(e.available_at,e.id))))


def suspend_stories(result, gaps, bars_by_tf, policy):
    """Suspend inference across gaps; retain original story and positions."""
    if not gaps:return result
    bars={bar.id:bar for rows in bars_by_tf.values() for bar in rows}
    additions=[]
    for story in result.stories:
        reaction=bars.get(story.details.get('reaction_bar_id'))
        origin_end=reaction.end if reaction is not None else story.clock.occurred_to
        for gap in gaps:
            if origin_end>gap.clock.occurred_from:continue
            at=max(story.available_at,gap.available_at)
            additions.append(Event(id=stable_id('story_suspended',story.id,gap.id,policy.id),
                kind='STORY_SUSPENDED',instrument=story.instrument,tf=story.origin_tf,
                clock=Clock(gap.clock.occurred_from,gap.clock.occurred_to,at),
                side=story.side,reference_id=story.id,evidence_ids=(story.id,gap.id),
                bar_ids=gap.bar_ids,policy_id=policy.id,evidence_status='UNKNOWN',
                details={'reason':'BASE_DATA_GAP','pending_action':'CANCEL_DEPENDENT',
                         'position_action':'NONE','market_reversal':False}))
            break
    return replace(result,events=tuple(sorted((*result.events,*additions),key=lambda e:(e.available_at,e.id))))
