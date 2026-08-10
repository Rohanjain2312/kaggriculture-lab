from kaggle_environments import make

env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.run(["main.py", "starter"])

final = env.steps[-1]
for i, s in enumerate(final):
    money = s.observation.farms[i]["money"]
    print(f"Player {i}: status={s.status}, final money={money:.2f}")