"""Strict OHLC execution with immutable causal event history."""
from bisect import bisect_right
from itertools import islice
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from .types import Clock, Event, utc, stable_id
from .aggregation import expected_slots


@dataclass(frozen=True)
class Costs:
    spread_ticks: Decimal = Decimal('0')
    entry_slippage_ticks: Decimal = Decimal('0')
    stop_slippage_ticks: Decimal = Decimal('0')
    commission_ticks: Decimal = Decimal('0')  # full round trip per unit
    financing_ticks: Decimal = Decimal('0')
    def __post_init__(self):
        for k in self.__dataclass_fields__:
            v=Decimal(str(getattr(self,k)))
            if not v.is_finite() or v<0: raise ValueError('finite nonnegative explicit costs required')
            object.__setattr__(self,k,v)


def simulate(orders,bars,instrument,costs,as_of,actions=(), *, calendar=None):
    if isinstance(costs,dict): costs=Costs(**costs)
    if not isinstance(costs,Costs): raise ValueError('Costs required')
    if instrument.price_basis!='BID': raise ValueError('simulation currently requires BID bars and declared spread hypothesis')
    calendar=calendar or instrument.calendar_id
    clock=utc(as_of); bars=tuple(b for b in bars if b.available_at<=clock)
    if any(not b.complete for b in bars): raise ValueError('complete execution bars required')
    if any(b.instrument!=instrument.symbol for b in bars): raise ValueError('mixed instruments')
    if any(a.start>=b.start for a,b in zip(bars,bars[1:])): raise ValueError('bars must be ordered unique')
    ends=[b.end for b in bars]
    policy=stable_id('execution_policy','strict_sequence_v2',costs,instrument)
    events=[]; observations=[]; positions=[]
    def emit(o,kind,at,lo=None,price=None,details=None,bar=None):
        e=Event(id=stable_id('execution',o.id,kind,at,lo,price,details,policy),kind=kind,instrument=o.instrument,tf=o.tf,clock=Clock(lo or at,at,at),side=o.side,reference_id=o.id,price_ticks=price if isinstance(price,int) else None,policy_id=policy,bar_ids=(bar.id,) if bar else (),details=details or {})
        events.append(e); return e
    for o in sorted(orders,key=lambda x:(x.available_at,x.id)):
        if o.available_at>clock: continue
        if o.instrument!=instrument.symbol: raise ValueError('order instrument mismatch')
        state='PENDING'; outcome='OPEN'; stop=Decimal(o.stop_ticks); target=Decimal(o.target_ticks)
        fill=None; fill_window=None; remaining=o.quantity; realized=Decimal(0); risk=None; censored=None
        management=[]; current=o.available_at
        acts=sorted((dict(a) for a in actions if a.get('order_id')==o.id and utc(a.get('available_at',a.get('at')))<=clock),key=lambda a:utc(a.get('available_at',a.get('at'))))
        for a in acts:
            a['_at']=utc(a.get('available_at',a.get('at')))
            if a.get('kind','').upper() not in ('CANCEL','REPLACE','AMEND','BREAK_EVEN','PARTIAL','MANUAL_CLOSE'):
                raise ValueError('unsupported action kind')
            for field in ('stop_ticks','target_ticks','price_ticks','quantity'):
                if field not in a: continue
                try: value=Decimal(str(a[field]))
                except (InvalidOperation, ValueError, TypeError) as exc:
                    raise ValueError('invalid action '+field) from exc
                if not value.is_finite() or isinstance(a[field],bool):
                    raise ValueError('finite action '+field+' required')
                if field=='quantity':
                    if value<=0: raise ValueError('positive action quantity required')
                elif value!=value.to_integral_value():
                    raise ValueError('action prices must use whole instrument ticks')
                a[field]=value
            if a['_at']<o.available_at: raise ValueError('action precedes order')
            if a.get('occurred_at') and utc(a['occurred_at'])!=a['_at']: raise ValueError('retroactive actions unsupported')
        ai=0
        emit(o,'ORDER_SUBMITTED',o.available_at,details={'kind':o.kind,'initial_entry_ticks':o.entry_ticks,'initial_stop_ticks':o.stop_ticks,'initial_target_ticks':o.target_ticks,'quantity':str(o.quantity)})
        def censor(reason,at,lo=None,bar=None):
            nonlocal state,outcome,censored
            censored=reason; outcome='CENSORED'; state='CENSORED' if fill is None else 'FILLED'
            emit(o,'EXECUTION_CENSORED',at,lo,details={'reason':reason},bar=bar)
        def close(price,qty,kind,at,lo=None,bar=None):
            nonlocal remaining,realized,state,outcome
            signed=(price-fill)*(1 if o.side=='BUY' else -1)
            realized+=(signed-costs.commission_ticks-costs.financing_ticks)*qty
            remaining-=qty
            emit(o,kind,at,lo,details={'price_ticks':str(price),'quantity':str(qty),'remaining':str(remaining)},bar=bar)
            if remaining==0: state='CLOSED'; outcome='WIN' if realized>0 else 'LOSS' if realized<0 else 'BREAK_EVEN'
        def amend(a,kind,at):
            nonlocal stop,target
            new_stop=a.get('stop_ticks',fill if kind=='BREAK_EVEN' else stop)
            new_target=a.get('target_ticks',target)
            if not (new_stop<new_target if o.side=='BUY' else new_target<new_stop):
                raise ValueError('invalid amended stop/target geometry')
            if new_stop!=new_stop.to_integral_value() or new_target!=new_target.to_integral_value():
                raise ValueError('amended prices must use whole instrument ticks')
            stop,target=new_stop,new_target
            emit(o,'POSITION_AMENDED',at,details={'stop_ticks':str(stop),'target_ticks':str(target)})
            management.append(a)
        for b in islice(bars,bisect_right(ends,o.available_at),None):
            if state not in ('PENDING','FILLED') or censored: break
            # A missing active interval must be encountered before later OHLC.
            if b.start>current and list(expected_slots(current,b.start,b.tf,calendar)):
                censor('MISSING_ACTIVE_DATA',b.start); break
            if b.start<o.available_at<b.end:
                censor('SUBMISSION_INSIDE_BAR',b.available_at,b.start,b); break
            if b.start<current: continue
            # Boundary actions precede the following executable open.
            while ai<len(acts) and acts[ai]['_at']<=b.start:
                a=acts[ai]; ai+=1; kind=a.get('kind','').upper(); at=a['_at']
                if kind in ('CANCEL','REPLACE') and fill is None:
                    state='CANCELLED' if kind=='CANCEL' else 'REPLACED'; outcome=state
                    emit(o,'ORDER_'+state,at,details={k:v for k,v in a.items() if not k.startswith('_')}); break
                if kind in ('AMEND','BREAK_EVEN') and fill is not None:
                    amend(a,kind,at)
                elif kind in ('PARTIAL','MANUAL_CLOSE') and fill is not None:
                    qty=Decimal(str(a.get('quantity',remaining)))
                    if qty<=0 or qty>remaining: raise ValueError('invalid exit quantity')
                    if 'price_ticks' not in a: raise ValueError('manual/partial action needs explicit price_ticks')
                    close(Decimal(str(a['price_ticks'])),qty,'POSITION_'+kind,at); management.append(a)
                elif kind not in ('CANCEL','REPLACE','AMEND','BREAK_EVEN','PARTIAL','MANUAL_CLOSE'): raise ValueError('unsupported action kind')
            if state not in ('PENDING','FILLED'): break
            if fill is None and o.expires_at is not None and o.expires_at<=b.start:
                state='MISSED'; outcome='EXPIRED'; emit(o,'ORDER_EXPIRED',o.expires_at); break
            boundary=min([a['_at'] for a in acts[ai:ai+1]]+([o.expires_at] if fill is None and o.expires_at else []),default=b.end)
            if b.start<boundary<b.end:
                censor('ACTION_OR_EXPIRY_INSIDE_BAR',b.available_at,b.start,b); break
            just=False
            if fill is None:
                touched=o.kind=='MARKET' or (Decimal(b.low_ticks)+costs.spread_ticks<=o.entry_ticks if o.side=='BUY' else b.high_ticks>=o.entry_ticks)
                if not touched: current=b.end; continue
                fill=(Decimal(b.open_ticks)+(costs.spread_ticks+costs.entry_slippage_ticks if o.side=='BUY' else -costs.entry_slippage_ticks)) if o.kind=='MARKET' else Decimal(o.entry_ticks)
                risk=abs(fill-Decimal(o.stop_ticks))
                if risk==0 or (o.side=='BUY' and not stop<fill<target) or (o.side=='SELL' and not target<fill<stop):
                    censor('INVALID_FILL_RISK',b.available_at,b.start,b); break
                state='FILLED'; just=True; fill_window={'start':b.start,'end':b.end,'observed_at':b.available_at}
                emit(o,'ORDER_FILLED',b.available_at,b.start,details={'fill_ticks':str(fill),'quantity':str(o.quantity),'kind':o.kind},bar=b)
            stop_hit=b.low_ticks<=stop if o.side=='BUY' else Decimal(b.high_ticks)+costs.spread_ticks>=stop
            target_hit=b.high_ticks>=target if o.side=='BUY' else Decimal(b.low_ticks)+costs.spread_ticks<=target
            if (stop_hit and target_hit) or (just and o.kind=='LIMIT' and (stop_hit or target_hit)):
                censor('UNRESOLVED_INTRABAR_SEQUENCE',b.available_at,b.start,b); break
            if stop_hit:
                px=min(stop,Decimal(b.open_ticks))-costs.stop_slippage_ticks if o.side=='BUY' else max(stop,Decimal(b.open_ticks)+costs.spread_ticks)+costs.stop_slippage_ticks
                close(px,remaining,'POSITION_STOPPED',b.available_at,b.start,b)
            elif target_hit: close(target,remaining,'POSITION_TARGET',b.available_at,b.start,b)
            current=b.end
        if not censored and state in ('PENDING','FILLED'):
            if current<clock and list(expected_slots(current,clock,bars[0].tf if bars else 'M1',calendar)):
                # A currently forming final candle is not a missing completed interval.
                duration=bars[-1].end-bars[-1].start if bars else timedelta(minutes=1)
                if current+duration<=clock: censor('MISSING_ACTIVE_DATA',clock)
        # Actions at the final observed boundary need no following candle.
        if not censored and state in ('PENDING','FILLED'):
            while ai<len(acts) and acts[ai]['_at']<=clock:
                a=acts[ai]; ai+=1; at=a['_at']; kind=a.get('kind','').upper()
                if at>current and next(expected_slots(current,at,bars[0].tf if bars else 'M1',calendar),None) is not None:
                    censor('ACTION_INSIDE_UNOBSERVED_INTERVAL',at,current); break
                if kind in ('CANCEL','REPLACE') and fill is None:
                    state='CANCELLED' if kind=='CANCEL' else 'REPLACED'; outcome=state
                    emit(o,'ORDER_'+state,at,details={k:v for k,v in a.items() if not k.startswith('_')}); break
                if kind in ('AMEND','BREAK_EVEN') and fill is not None:
                    amend(a,kind,at)
                elif kind in ('PARTIAL','MANUAL_CLOSE') and fill is not None:
                    qty=Decimal(str(a.get('quantity',remaining)))
                    if qty<=0 or qty>remaining or 'price_ticks' not in a: raise ValueError('explicit valid manual exit required')
                    close(Decimal(str(a['price_ticks'])),qty,'POSITION_'+kind,at); management.append(a)
                    if state=='CLOSED': break
        if state=='PENDING' and o.expires_at and o.expires_at<=clock and not censored:
            state='MISSED';outcome='EXPIRED';emit(o,'ORDER_EXPIRED',o.expires_at)
        obs={'id':o.id,'setup_id':o.setup_id,'status':state,'outcome':outcome,'fill_ticks':str(fill) if fill is not None else None,'fill_window':fill_window,'remaining_quantity':str(remaining if fill is not None else 0),'realized_ticks_quantity':str(realized),'net_r':str(realized/(risk*o.quantity)) if risk and remaining==0 else None,'censor_reason':censored,'initial_stop_ticks':o.stop_ticks,'initial_target_ticks':o.target_ticks,'costs':costs,'management':[{k:v for k,v in a.items() if not k.startswith('_')} for a in management]}
        observations.append(obs)
        if fill is not None: positions.append({'order_id':o.id,'fill_ticks':str(fill),'remaining_quantity':str(remaining),'stop_ticks':str(stop),'target_ticks':str(target),'state':state,'realized_ticks_quantity':str(realized)})
    events.sort(key=lambda e:e.available_at)
    return {'events':tuple(events),'observations':observations,'positions':positions,'policy_id':policy}
