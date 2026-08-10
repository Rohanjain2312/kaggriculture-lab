import json, os, glob, statistics as st, math, sys
sys.path.insert(0,"/private/tmp/claude-501/-Users-rohanjain-Kaggle/42595745-fed2-4e70-8549-75107f5a1ad2/scratchpad")
from sim import price
EX="/private/tmp/claude-501/-Users-rohanjain-Kaggle/42595745-fed2-4e70-8549-75107f5a1ad2/scratchpad/ex"
PRODUCTS=["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]
SHOPS={"BAKERY":["EGG","WHEAT"],"PIZZA_SHOP":["MILK","TOMATO","WHEAT"],"BRUNCH_SPOT":["EGG","WHEAT","STRAWBERRY"],
"YARN_STORE":["WOOL"],"ICE_CREAM_SHOP":["STRAWBERRY","MILK","WHEAT"],"PET_CAFE":["CARROT"],
"SMOOTHIE_SHOP":["STRAWBERRY","MILK"],"FARMERS_MARKET":["WHEAT","CARROT","TOMATO","STRAWBERRY"]}
def drain_series(e):
    old = e['ver']=='1.32.5'
    d={p:[0]*e['n'] for p in PRODUCTS}
    sched=e['shops']; idx=0; cur=[]
    for i in range(1,e['n']):
        step=i-1
        while idx<len(sched) and sched[idx][0]<=step: cur=sched[idx][1]; idx+=1
        if step%4==0:
            for s in cur:
                pr=SHOPS[s]; m=2 if len(pr)==1 else 1
                for it in pr: d[it][i]+=m
        if step%e['tci']==0:
            day=step//24
            mult=(1 if day<10 else (2 if day<20 else 4)) if old else 1
            for it in PRODUCTS:
                if it!="FERTILIZER": d[it][i]+=mult
    return d
def load():
    out=[]
    for f in sorted(os.listdir(EX)):
        out.append(json.load(open(os.path.join(EX,f))))
    return out
def flows(e):
    """per-product per-step net market flow (positive = net sold into market)"""
    d=drain_series(e)
    fl={}
    for k,p in enumerate(PRODUCTS):
        fl[p]=[0]*e['n']
        for i in range(1,e['n']):
            fl[p][i]=e['inv'][i][k]-e['inv'][i-1][k]+d[p][i]
    return fl,d
