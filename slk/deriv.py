"""Deriv public Options market-data feed. No account token, broker orders or MT5.

DV-prefixed internal keys isolate this provider from IC Markets; original broker
symbols (including underscores/case) are retained for API requests.
"""
import json
import math
import re
import time
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from .instruments import norm

URL='wss://api.derivws.com/trading/v1/options/ws/public'
CATALOGUE=Path(__file__).resolve().parents[1]/'data'/'deriv_symbols.json'


def key(symbol):
    value='DV'+norm(symbol)
    if not re.fullmatch('[A-Z0-9]{3,12}',value):raise ValueError('unsupported Deriv symbol length')
    return value


def catalogue(symbols):
    out={}
    for s in symbols:
        symbol=s.get('underlying_symbol') or s.get('symbol')
        if not symbol or s.get('is_trading_suspended'):continue
        try:k=key(symbol)
        except ValueError:continue
        pip=float(s.get('pip_size') or s.get('pip') or 0)
        if not math.isfinite(pip) or pip<=0:continue
        digits=max(0,-Decimal(str(pip)).normalize().as_tuple().exponent)
        if not math.isclose(pip,10.0**-digits,rel_tol=1e-10):continue
        quote_increment=pip
        # Preserve established FX/metals/index strategy pip units independently of quote precision.
        underlying=re.sub('^FRX','',str(symbol).upper())
        if s.get('market')=='forex' and re.fullmatch('[A-Z]{6}',underlying):
            pip=.01 if underlying.endswith('JPY') else .0001
        elif s.get('market')=='commodities':
            from .instruments import static
            pip=static(underlying)[0]
        elif s.get('market')=='indices':pip=1.0
        pip_position=max(0,-Decimal(str(pip)).normalize().as_tuple().exponent)
        if k in out and out[k]['symbol']!=symbol:raise ValueError('Deriv key collision')
        out[k]=dict(key=k,symbol=symbol,name=s.get('underlying_symbol_name') or s.get('display_name') or symbol,
                    market=s.get('market'),exchange_is_open=bool(s.get('exchange_is_open',True)),pip=pip,quote_increment=quote_increment,digits=digits,pip_position=pip_position,
                    provider='Deriv')
    if not out:raise ValueError('empty Deriv catalogue')
    return list(out.values())


def _open_socket(*args,**kwargs):
    import websocket
    return websocket.create_connection(*args,**kwargs)


class Feed:
    max_span=30*86400 # <=720 H1 bars, below observed public endpoint1000-bar cap
    def __init__(self,socket_factory=None,deadline=None):
        self.factory=socket_factory;self.ws=None;self.symbols={};self.request_id=0
        self.last=0;self.deadline=deadline or time.monotonic()+300
    def __enter__(self):
        if self.factory is None:
            self.factory=_open_socket
        self.ws=self.factory(URL,timeout=20)
        return self
    def __exit__(self,*a):
        if self.ws:self.ws.close()
    def request(self,payload):
        if time.monotonic()>=self.deadline:raise TimeoutError('Deriv data budget elapsed')
        gap=.3-(time.monotonic()-self.last)
        if gap>0:time.sleep(gap)
        self.request_id+=1;rid=self.request_id
        self.ws.send(json.dumps({**payload,'req_id':rid}));self.last=time.monotonic()
        for _ in range(10):
            reply=json.loads(self.ws.recv())
            if reply.get('req_id')!=rid:continue
            if reply.get('error'):raise RuntimeError('Deriv '+str(reply['error'].get('code','request failed')))
            return reply
        raise RuntimeError('Deriv response mismatch')
    def prefetch(self,pairs=None):
        rows=catalogue(self.request({'active_symbols':'brief'})['active_symbols'])
        self.symbols={r['key']:r for r in rows}
        if pairs:
            for pair in pairs:self.info(pair)
        return rows
    def info(self,pair):
        if pair not in self.symbols:raise ValueError(f'{pair}: not found in Deriv public catalogue')
        return self.symbols[pair]
    def bars(self,pair,lo,hi):
        symbol=self.info(pair)['symbol']
        rows=[]
        for start in range(int(lo),int(hi),self.max_span):
            end=min(int(hi),start+self.max_span)
            reply=self.request({'ticks_history':symbol,'start':start,'end':str(end-1),
                                'style':'candles','granularity':3600,'count':min(1000,(end-start+3599)//3600)})
            values=reply.get('candles')
            if not isinstance(values,list):raise ValueError('Deriv candles missing')
            for c in values:
                t=int(c['epoch']);o,h,l,cl=(float(c[k]) for k in ('open','high','low','close'))
                if not start<=t<end:continue
                if t%3600:continue  # inception/partial first bar is not a completed aligned hour
                if not all(math.isfinite(x) and x>0 for x in (o,h,l,cl)) or l>min(o,cl) or h<max(o,cl) or l>h:
                    raise ValueError('invalid Deriv H1 candle')
                rows.append((t,o,h,l,cl))
            # A request below5000 must not silently truncate a continuous synthetic interval.
            if len(values)>5000:raise ValueError('Deriv history response unreasonably large')
        rows=sorted({r[0]:r for r in rows}.values())
        if self.info(pair).get('market') in ('synthetic_index','cryptocurrency') and rows:
            if any(b[0]-a[0]!=3600 for a,b in zip(rows,rows[1:])):
                raise ValueError('Deriv continuous-market history gap')
            if rows[-1][0]<int(hi)-3600:
                raise ValueError('Deriv continuous-market history missing end')
        return rows


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--pair',default='DV1HZ100V');p.add_argument('--days',type=int,default=30)
    p.add_argument('--catalogue',action='store_true');p.add_argument('--probe',action='store_true')
    args=p.parse_args()
    with Feed() as feed:
        rows=feed.prefetch()
        if args.catalogue:
            CATALOGUE.parent.mkdir(exist_ok=True)
            CATALOGUE.write_text(json.dumps(dict(provider='Deriv public API',updated_at=datetime.now(timezone.utc).isoformat(),symbols=rows),indent=2)+'\n')
            print(f'Deriv catalogue: {len(rows)} symbols')
        if args.probe:
            from . import store,candles,live
            now=store._utc().floor('h')
            state=store.update(args.pair,now,days=args.days,source='deriv',feed=feed)
            h=state.frame()
            res=live.compute_pair((args.pair,now,live.state_stories(['D','W','M'],live.DEFAULT),['D','W','M'],
                                   live.DEFAULT,live.ENTRY_DEFAULT,True))
            if 'error' in res:raise RuntimeError(res['error'])
            print(json.dumps(dict(pair=args.pair,source=state.src,h1=len(h),stories=len(res['rows']),
                                  entry_candidates=len(res['entries']),full_pipeline=True,clock='UTC',
                                  closed_h1_only=bool((h.index+__import__('pandas').Timedelta(hours=1)<=now).all()))))


if __name__=='__main__':main()
