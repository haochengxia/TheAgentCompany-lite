
<div style="text-align: center;">
  <img src="/docs/assets/logo.svg" alt="atc-lite-logo"/>
</div>

We are aimed to offer researcher-friendly benchmarks.

```
Original：                        V2：
serial ──→ task ──→ task      Round ──→ group ──→ instance ──→ task
              │          │               │           │           task
              ↓          ↓               │           │
           ~17.5h      ~700GB             │           instance ──→ task
                                          │                       task
                                          group ──→ instance ──→ task
                                                    instance ──→ task
                                          group ──→ instance ──→ task
```

In the original version of TheAgentCompany, all tasks serial execution and evalute

  1. pull / construct 175 task images
  2. docker run → start OpenHands runtime
  3. inject instruction + task files
  4. wait agent finish
  5. eval
  6. destory container
  7. invoke api-server reset corresponidng service（gitlab/rocketchat/owncloud…）
  8. wait service be healthy 

