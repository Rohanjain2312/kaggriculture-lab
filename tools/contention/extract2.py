import json, os, sys
from collections import defaultdict
OUT="/private/tmp/claude-501/-Users-rohanjain-Kaggle/42595745-fed2-4e70-8549-75107f5a1ad2/scratchpad/ex2"
def census(farm):
    c=defaultdict(int)
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t,dict):
                k=t.get("kind")
                if k=="PLANT":
                    c["crop_"+t["crop"]]+=1; c["yld_"+t["crop"]]+=t.get("yield_units",0)
                elif k in ("PASTURE","COOP"):
                    a=t.get("animal")
                    if a: c["an_"+a]+=1
                    else: c["struct_"+k]+=1
                elif k=="WEED": c["weed"]+=1
                else: c[k.lower()]+=1
            elif t=="LOCKED": c["locked"]+=1
            else: c["empty"]+=1
    return dict(c)
def run(path):
    d=json.load(open(path)); eid=os.path.basename(path)[:-5]
    out={"id":eid,"names":d["info"]["TeamNames"],"rewards":d["rewards"],"daily":[{},{}],"hands":[{},{}],"pos":[{},{}]}
    for i,s in enumerate(d["steps"]):
        o=s[0]["observation"]
        if o["hour"]==12:
            for p in (0,1):
                f=o["farms"][p]
                out["daily"][p][o["day"]]=census(f)
                out["hands"][p][o["day"]]=len(f["hands"])
    json.dump(out,open(os.path.join(OUT,eid+".json"),"w"))
    return eid
if __name__=="__main__":
    for p in sys.argv[1:]: print(run(p),flush=True)
