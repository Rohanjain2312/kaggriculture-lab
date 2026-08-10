"""Faithful market replay of a Kaggriculture episode -> exact per-player revenue by product."""
import json, math, sys, os, glob

MARKET_I0 = 10000
PRICE_FLOOR = 1
PRODUCTS = ["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]
MP = {
 "WHEAT":dict(base=25,T=400,bf="sqrt",bt=.80,af="log",at=.20),
 "CARROT":dict(base=35,T=450,bf="log",bt=.20,af="sqrt",at=.70),
 "TOMATO":dict(base=60,T=200,bf="linear",bt=.40,af="sqrt",at=.60),
 "STRAWBERRY":dict(base=120,T=100,bf="sqrt",bt=.70,af="linear",at=1.60),
 "MELON":dict(base=250,T=300,bf="log",bt=.20,af="sq",at=3.60),
 "EGG":dict(base=50,T=332,bf="linear",bt=.40,af="log",at=.20),
 "MILK":dict(base=160,T=122,bf="sqrt",bt=.60,af="linear",at=1.60),
 "WOOL":dict(base=200,T=105,bf="log",bt=.20,af="sq",at=3.20),
 "FERTILIZER":dict(base=100,T=200,bf="linear",bt=.40,af="linear",at=.40),
}
CROPS={"WHEAT":10,"CARROT":20,"TOMATO":50,"STRAWBERRY":100,"MELON":80}
ANIMALS={"GOOSE":300,"COW":400,"SHEEP":500}
LAND_PRICES=[1000,2000,4000]

def shape(f,x):
    x=max(0.0,x)
    return {"linear":x,"sq":x*x,"sqrt":math.sqrt(x),"log":math.log(1+x)}[f]

def price(item,inv):
    p=MP[item]
    if inv<MARKET_I0:
        amp=p["bt"]*p["base"]/shape(p["bf"],p["T"]); v=p["base"]+amp*shape(p["bf"],MARKET_I0-inv)
    else:
        amp=p["at"]*p["base"]/shape(p["af"],p["T"]); v=p["base"]-amp*shape(p["af"],inv-MARKET_I0)
    return max(PRICE_FLOOR,int(round(v)))

def fib(n):
    a,b=1,1
    for _ in range(n): a,b=b,a+b
    return a

SHED_ACCESS={(4,4),(5,4),(4,5),(5,5)}

def parse_order(o):
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

def analyse(path):
    d=json.load(open(path))
    steps=d["steps"]; cfg=d["configuration"]
    center_iv=cfg["townCenterSellInterval"]; shop_iv=cfg["townShopSellInterval"]
    modv=d.get("module_version","1.32.6")
    new_env = tuple(int(x) for x in modv.split(".")) >= (1,32,6)
    n=len(steps)
    # tracked state
    market={it:MARKET_I0 for it in PRODUCTS}
    money=[3000.0,3000.0]
    rev={p:{it:0.0 for it in PRODUCTS} for p in (0,1)}
    units={p:{it:0 for it in PRODUCTS} for p in (0,1)}
    buy_units={p:{it:0 for it in PRODUCTS} for p in (0,1)}
    buy_cost={p:{it:0.0 for it in PRODUCTS} for p in (0,1)}
    spend={p:{"HIRE":0.0,"LAND":0.0,"SEED":0.0,"ANIMAL":0.0} for p in (0,1)}
    animals_bought={p:{a:0 for a in ANIMALS} for p in (0,1)}
    seeds_bought={p:{c:0 for c in CROPS} for p in (0,1)}
    hires_per_day={p:[0]*30 for p in (0,1)}
    inv_path={it:[] for it in PRODUCTS}
    price_path={it:[] for it in PRODUCTS}

    for i in range(1,n):
        prev=steps[i-1]
        obs0=prev[0]["observation"]
        step=obs0.get("step", i-1)
        day=step//24
        farms=obs0["farms"]
        sheds=[]
        for p in (0,1):
            pr=prev[p]["observation"]["private"]
            sheds.append(dict(pr["shed"]))
        # apply unit actions that touch the shed (PICKUP / DROP / PLACE-to-shed)
        for p in (0,1):
            act=steps[i][p].get("action") or {}
            if not isinstance(act,dict): act={}
            pr=prev[p]["observation"]["private"]
            invs=pr["inventories"]
            farm=farms[p]
            units_pos=[tuple(farm["farmer"])]+[tuple(h) for h in farm["hands"]]
            ua=[act.get("farmer",["PASS"])]+list(act.get("hands",[]) or [])
            for idx,a in enumerate(ua):
                if idx>=len(units_pos): break
                if not isinstance(a,list) or not a: continue
                pos=units_pos[idx]; op=a[0]
                if op=="PICKUP" and pos in SHED_ACCESS and len(a)>=2:
                    it=a[1]; q=int(a[2]) if len(a)>=3 else 1
                    q=min(q,sheds[p].get(it,0))
                    if q>0: sheds[p][it]-=q
                elif op=="DROP" and pos in SHED_ACCESS:
                    fi=invs[idx] if idx<len(invs) else {}
                    for it,q in fi.items():
                        if q>0:
                            room=max(0,100-sum(sheds[p].values()))
                            sheds[p][it]=sheds[p].get(it,0)+min(q,room)
                elif op=="PLACE" and pos in SHED_ACCESS and len(a)>=2:
                    it=a[1]
                    fi=invs[idx] if idx<len(invs) else {}
                    if it not in ANIMALS or fi.get(it,0)>0:
                        q=int(a[2]) if len(a)>=3 else 1
                        q=min(q,fi.get(it,0))
                        room=max(0,100-sum(sheds[p].values()))
                        q=min(q,room)
                        if q>0: sheds[p][it]=sheds[p].get(it,0)+q
        # ---- market ----
        queues=[]
        for p in (0,1):
            act=steps[i][p].get("action") or {}
            m=act.get("market",[]) if isinstance(act,dict) else []
            queues.append(list(m)[:10] if isinstance(m,list) else [])
        hires_today=[farms[0].get("hires_today",0),farms[1].get("hires_today",0)]
        nq=len(farms[0]["unlocked_quadrants"]),len(farms[1]["unlocked_quadrants"])
        nq=[nq[0]-1,nq[1]-1]
        maxlen=max((len(q) for q in queues),default=0)
        for k in range(maxlen):
            ost=[parse_order(q[k]) if k<len(q) else None for q in queues]
            for p in (0,1):
                if ost[p] is None: continue
                t=ost[p]["type"]
                if t=="HIRE":
                    c=fib(hires_today[p])
                    if money[p]>=c:
                        money[p]-=c; hires_today[p]+=1; spend[p]["HIRE"]+=c
                        hires_per_day[p][min(day,29)]+=1
                    ost[p]=None
                elif t=="BUY_LAND":
                    if nq[p]<3:
                        c=LAND_PRICES[nq[p]]
                        if money[p]>=c: money[p]-=c; nq[p]+=1; spend[p]["LAND"]+=c
                    ost[p]=None
            guard=0
            while True:
                guard+=1
                if guard>100000: break
                quoted=[None,None]
                for p in (0,1):
                    o=ost[p]
                    if o is None or o.get("remaining",0)<=0: continue
                    t=o["type"]; it=o["item"]
                    if t=="SELL" and it in PRODUCTS:
                        quoted[p]=("SELL",it,price(it,market[it]),o)
                    elif t=="BUY_PRODUCT" and it in ("WHEAT","FERTILIZER"):
                        quoted[p]=("BUY_PRODUCT",it,price(it,market[it]-1),o)
                    elif t=="BUY_SEED" and it in CROPS:
                        quoted[p]=("BUY_SEED",it,CROPS[it],o)
                    elif t=="BUY_ANIMAL" and it in ANIMALS:
                        quoted[p]=("BUY_ANIMAL",it,ANIMALS[it],o)
                    else: ost[p]=None
                if all(q is None for q in quoted): break
                committed=False
                for p in (0,1):
                    q=quoted[p]
                    if q is None: continue
                    op,it,pz,o=q; ok=False
                    if op=="SELL":
                        if sheds[p].get(it,0)>0:
                            sheds[p][it]-=1; money[p]+=pz
                            rev[p][it]+=pz; units[p][it]+=1
                            if pz>1: market[it]+=1
                            ok=True
                    elif op=="BUY_PRODUCT":
                        if money[p]>=pz and sum(sheds[p].values())<100:
                            money[p]-=pz; sheds[p][it]=sheds[p].get(it,0)+1
                            market[it]-=1; buy_units[p][it]+=1; buy_cost[p][it]+=pz; ok=True
                    elif op=="BUY_SEED":
                        if money[p]>=pz:
                            money[p]-=pz; spend[p]["SEED"]+=pz; seeds_bought[p][it]+=1; ok=True
                    elif op=="BUY_ANIMAL":
                        if money[p]>=pz and sum(sheds[p].values())<100:
                            money[p]-=pz; sheds[p][it]=sheds[p].get(it,0)+1
                            spend[p]["ANIMAL"]+=pz; animals_bought[p][it]+=1; ok=True
                    if ok: o["remaining"]-=1; committed=True
                    else: ost[p]=None
                if not committed: break
        # ---- town drain ----
        shops=obs0["town"].get("unlocked_shops",[])
        SHOPS={"BAKERY":["EGG","WHEAT"],"PIZZA_SHOP":["MILK","TOMATO","WHEAT"],
               "BRUNCH_SPOT":["EGG","WHEAT","STRAWBERRY"],"YARN_STORE":["WOOL"],
               "ICE_CREAM_SHOP":["STRAWBERRY","MILK","WHEAT"],"PET_CAFE":["CARROT"],
               "SMOOTHIE_SHOP":["STRAWBERRY","MILK"],
               "FARMERS_MARKET":["WHEAT","CARROT","TOMATO","STRAWBERRY"]}
        if step % shop_iv == 0:
            for sn in shops:
                pr_=SHOPS[sn]; mult=2 if len(pr_)==1 else 1
                for it in pr_: market[it]-=mult
        if step % center_iv == 0:
            cmult = 1 if new_env else 2**(day//10)   # 1.32.5 scaled x1/x2/x4 by decade
            for it in PRODUCTS:
                if it!="FERTILIZER": market[it]-=cmult
        for it in PRODUCTS:
            inv_path[it].append(market[it]); price_path[it].append(price(it,market[it]))
    return dict(path=path, modv=modv, new_env=new_env, id=d.get("id"), rewards=d["rewards"], names=d["info"]["TeamNames"],
                center_iv=center_iv, money=money, rev=rev, units=units,
                buy_units=buy_units, buy_cost=buy_cost, spend=spend,
                animals=animals_bought, seeds=seeds_bought, market_final=market,
                inv_path=inv_path, price_path=price_path, hires_per_day=hires_per_day,
                shops=steps[-1][0]["observation"]["town"]["unlocked_shops"])

if __name__=="__main__":
    r=analyse(sys.argv[1])
    print("recon money", [round(m) for m in r["money"]], "actual", r["rewards"])
