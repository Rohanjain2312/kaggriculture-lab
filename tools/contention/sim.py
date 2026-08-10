"""Replay the market lockstep to attribute revenue per player per product."""
import math, json, os
PRODUCTS = ["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]
PI = {p:i for i,p in enumerate(PRODUCTS)}
MP = {
 "WHEAT":{"base":25,"T":400,"bf":"sqrt","bt":0.80,"af":"log","at":0.20},
 "CARROT":{"base":35,"T":450,"bf":"log","bt":0.20,"af":"sqrt","at":0.70},
 "TOMATO":{"base":60,"T":200,"bf":"linear","bt":0.40,"af":"sqrt","at":0.60},
 "STRAWBERRY":{"base":120,"T":100,"bf":"sqrt","bt":0.70,"af":"linear","at":1.60},
 "MELON":{"base":250,"T":300,"bf":"log","bt":0.20,"af":"sq","at":3.60},
 "EGG":{"base":50,"T":332,"bf":"linear","bt":0.40,"af":"log","at":0.20},
 "MILK":{"base":160,"T":122,"bf":"sqrt","bt":0.60,"af":"linear","at":1.60},
 "WOOL":{"base":200,"T":105,"bf":"log","bt":0.20,"af":"sq","at":3.20},
 "FERTILIZER":{"base":100,"T":200,"bf":"linear","bt":0.40,"af":"linear","at":0.40},
}
I0=10000; FLOOR=1
def shape(f,x):
    x=max(0.0,x)
    if f=="linear": return x
    if f=="sq": return x*x
    if f=="sqrt": return math.sqrt(x)
    if f=="log": return math.log(1.0+x)
    return x
def price(item, inv):
    p=MP[item]; base=p["base"]
    if inv < I0:
        amp=p["bt"]*base/shape(p["bf"],p["T"]); v=base+amp*shape(p["bf"],I0-inv)
    else:
        amp=p["at"]*base/shape(p["af"],p["T"]); v=base-amp*shape(p["af"],inv-I0)
    return max(FLOOR, int(round(v)))
SEED={"WHEAT":10,"CARROT":20,"TOMATO":50,"STRAWBERRY":100,"MELON":80}
ANIMAL={"GOOSE":300,"COW":400,"SHEEP":500}
LAND=[2000,4000,8000]
def fib(n):
    a,b=1,1
    for _ in range(n): a,b=b,a+b
    return a
def parse(o):
    if not isinstance(o,list) or not o: return None
    op=o[0]
    if op in ("HIRE","BUY_LAND"): return {"type":op}
    if op in ("BUY_SEED","BUY_PRODUCT","BUY_ANIMAL","SELL"):
        if len(o)<3: return None
        try: n=int(o[2])
        except Exception: return None
        if n<=0: return None
        return {"type":op,"item":o[1],"remaining":n}
    return None

def simulate_turn(inv, queues, shed, money, hires_today, nquad, shed_cap=100, maxo=10):
    """inv: dict item->int (mutated). queues: [list,list]. shed: [dict,dict] (mutated).
    Returns per-player dict: {'sell':{item:(units,rev)}, 'buy':{item:(units,cost)}, 'spend':x, 'money_delta':x}"""
    res=[{"sell":{}, "buy":{}, "other":0.0, "delta":0.0} for _ in range(2)]
    qs=[list(q)[:maxo] for q in queues]
    ml=max((len(q) for q in qs), default=0)
    for i in range(ml):
        ost=[parse(q[i]) if i<len(q) else None for q in qs]
        for pid,o in enumerate(ost):
            if o is None: continue
            if o["type"]=="HIRE":
                c=fib(hires_today[pid]); hires_today[pid]+=1
                money[pid]-=c; res[pid]["other"]-=c; res[pid]["delta"]-=c
                ost[pid]=None
            elif o["type"]=="BUY_LAND":
                k=nquad[pid]-1
                if k<len(LAND) and money[pid]>=LAND[k]:
                    money[pid]-=LAND[k]; res[pid]["other"]-=LAND[k]; res[pid]["delta"]-=LAND[k]; nquad[pid]+=1
                ost[pid]=None
        while True:
            quoted=[None,None]
            for pid,o in enumerate(ost):
                if o is None or o["remaining"]<=0: continue
                t=o["type"]; it=o["item"]
                if t=="SELL" and it in PRODUCTS: quoted[pid]=("SELL",it,price(it,inv[it]),o)
                elif t=="BUY_PRODUCT" and it in ("WHEAT","FERTILIZER"): quoted[pid]=("BUY_PRODUCT",it,price(it,inv[it]-1),o)
                elif t=="BUY_SEED" and it in SEED: quoted[pid]=("BUY_SEED",it,SEED[it],o)
                elif t=="BUY_ANIMAL" and it in ANIMAL: quoted[pid]=("BUY_ANIMAL",it,ANIMAL[it],o)
                else: ost[pid]=None
            if all(q is None for q in quoted): break
            committed=False
            for pid,q in enumerate(quoted):
                if q is None: continue
                op,it,pr,o=q; ok=False
                if op=="SELL":
                    if shed[pid].get(it,0)>0:
                        shed[pid][it]-=1; money[pid]+=pr
                        u,r=res[pid]["sell"].get(it,(0,0.0)); res[pid]["sell"][it]=(u+1,r+pr)
                        res[pid]["delta"]+=pr
                        if pr>1: inv[it]+=1
                        ok=True
                elif op=="BUY_PRODUCT":
                    if money[pid]>=pr and sum(shed[pid].values())<shed_cap:
                        money[pid]-=pr; shed[pid][it]=shed[pid].get(it,0)+1; inv[it]-=1
                        u,r=res[pid]["buy"].get(it,(0,0.0)); res[pid]["buy"][it]=(u+1,r+pr)
                        res[pid]["delta"]-=pr; ok=True
                elif op=="BUY_SEED":
                    if money[pid]>=pr: money[pid]-=pr; res[pid]["other"]-=pr; res[pid]["delta"]-=pr; ok=True
                elif op=="BUY_ANIMAL":
                    if money[pid]>=pr: money[pid]-=pr; res[pid]["other"]-=pr; res[pid]["delta"]-=pr; ok=True
                if ok:
                    o["remaining"]-=1; committed=True
                else: ost[pid]=None
            if not committed: break
    return res
