The basic idea is to utilize `dependencies.yml` from each task. We walk through all tasks and divide them into different groups according to the services required.
```
("gitlab",)                              → 47 tasks
("owncloud", "rocketchat")               → 33 tasks
("owncloud",)                            → 33 tasks
("rocketchat",)                          → 24 tasks
("gitlab", "rocketchat")                 → 15 tasks
("plane",)                               → 6 tasks
```

Task in the same group using same services so they should be executed sequentially, otherwise they can be executed in parallel.

Then we use coloring algo to divide tasks intro different rounds (here we set `max_groups=4`)
```
  Round 1: gitlab(47) || owncloud+rocketchat(33) || plane(6) || no-deps(3)
  Round 2: owncloud(33) || rocketchat(24) || gitlab+plane(5)
  Round 3: gitlab+rocketchat(15)
  Round 4: plane+rocketchat(5) || gitlab+owncloud(2)
  Round 5-6: one task each round
```

Find instance to run task.
We heuristicly set 6 instances:
1. 3 gitlab only instances
2. 3 full stack instances




