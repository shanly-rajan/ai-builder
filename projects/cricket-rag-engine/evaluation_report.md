# 🏏 MCC Cricket Laws RAG Engine — Evaluation Report

> **Interpretation warning:** This is an illustrative snapshot from one live-provider
> run against the limited `data/sample/laws.txt` corpus. The labels below use simple
> law-number and string-presence heuristics; they do not prove verdict accuracy,
> semantic faithfulness, citation correctness, or zero hallucinations. See
> [`docs/evaluation.md`](docs/evaluation.md) for the methodology and known gaps.

## Summary Metrics
- **Total Scenarios Evaluated:** 15
- **Retrieval Heuristic Passes:** 15 / 15
- **Refusal Phrase Checks:** Included for DRS, Impact Player, and Free Hit scenarios; not a zero-hallucination guarantee

## Detailed Benchmark Results

| ID | Scenario Name | Expected Ref | Retrieved Laws | Retrieval heuristic | Answer string heuristic |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Non-Striker Run Out | Law 38.3 | 38, 34 | ✅ Pass | ✅ Grounded |
| 2 | Helmet Penalty | Law 28.3 | 19, 28, 34 | ✅ Pass | ✅ Grounded |
| 3 | Protecting Wicket with Boot | Law 34.3 | 38, 28, 34 | ✅ Pass | ✅ Grounded |
| 4 | Airborne Boundary Catch | Law 19.5 | 34, 28, 19 | ✅ Pass | ✅ Grounded |
| 5 | Striking Ball Twice for Runs | Law 34.1 | 38, 34 | ✅ Pass | ✅ Grounded |
| 6 | Ball Beyond Boundary Object | Law 19.4 | 34, 19 | ✅ Pass | ✅ Grounded |
| 7 | Batter Leaving Crease During Play | Law 38.1 | 38, 19, 28, 34 | ✅ Pass | ✅ Grounded |
| 8 | Refusal Test: Wide Ball DRS | Law REFUSAL | 19, 28, 34 | ✅ Pass | ✅ Grounded |
| 9 | Refusal Test: IPL Impact Player | Law REFUSAL | 38, 28, 34 | ✅ Pass | ✅ Grounded |
| 10 | Multiple Hits Solely Guarding Wicket | Law 34.3 | 38, 28, 34 | ✅ Pass | ✅ Grounded |
| 11 | Boundary Airborne Contact | Law 19.5 | 28, 19 | ✅ Pass | ✅ Grounded |
| 12 | Ball Hitting Protective Helmet on Turf | Law 28.3 | 34, 28, 19 | ✅ Pass | ✅ Grounded |
| 13 | Non-Striker Stealing Ground | Law 38.3 | 38, 28, 34 | ✅ Pass | ✅ Grounded |
| 14 | Ball Striking Fielder Grounded Beyond Rope | Law 19.4 | 34, 28, 19 | ✅ Pass | ✅ Grounded |
| 15 | Refusal Test: Free Hit No-Ball | Law REFUSAL | 28, 19, 34 | ✅ Pass | ✅ Grounded |

## Adjudication Logs

### Scenario 1: Non-Striker Run Out
**Expected:** Law 38.3 (OUT)

**Adjudication Output:**

> **VERDICT: OUT — Run out.**

The non-striker is liable to be Run out because the bowler broke the wicket before the instant at which the bowler would normally have been expected to release the ball.

- **Law 38.3.1:** From when the ball comes into play until the expected release point, the non-striker is liable to be Run out if out of their ground.
- **Law 38.1.1:** A batter is out Run out if, while the ball is in play, they are out of their ground and their wicket is put down by the fielding side.

**Umpire action:** Raise the index finger and signal **OUT**.

---

### Scenario 2: Helmet Penalty
**Expected:** Law 28.3 (5 PENALTY RUNS / DEAD BALL)

**Adjudication Output:**

> **VERDICT: DEAD BALL — 5 PENALTY RUNS AWARDED.**

Under **Law 28.3.1**, because the ball struck the fielding side’s helmet placed on the ground behind the wicket-keeper, the ball **immediately becomes dead** and **5 penalty runs** are awarded to the batting side.

Under **Law 28.3.2**, also award:

- Any runs completed by the batters before the ball struck the helmet; and
- The run in progress, if the batters had crossed at the instant the ball struck the helmet.

**Umpire action:** Signal **Dead Ball** immediately and award **5 penalty runs**, in addition to the applicable completed run(s) under Law 28.3.2.

---

### Scenario 3: Protecting Wicket with Boot
**Expected:** Law 34.3 (NOT OUT)

**Adjudication Output:**

> **VERDICT: NOT OUT.**

Under **Law 34.3.1**, the striker may hit the ball a second time with any part of their person—other than a hand not holding the bat—**solely to guard their wicket**. Kicking the ball away with the boot for that purpose is therefore lawful.

**Umpire action:**  
- Do **not** give the batter out Hit the ball twice.  
- Award **no runs** from the defensive kick, as required by **Law 34.3.1**.  
- No special signal is required; play continues unless another applicable event occurs.

---

### Scenario 4: Airborne Boundary Catch
**Expected:** Law 19.5 (NOT OUT / ILLEGAL CATCH)

**Adjudication Output:**

> **VERDICT: NOT OUT — FOUR RUNS**

The catch is illegal because, after landing beyond the boundary, the fielder’s last ground contact was beyond the rope. When he jumps back and touches the ball again, he is deemed **grounded beyond the boundary** while airborne.

- **Law 19.5.1:** A fielder airborne after last touching the ground beyond the boundary is grounded beyond the boundary.
- **Law 19.5.2:** A catch is not legal if the fielder touches the ball while grounded beyond the boundary.
- **Law 19.4.2:** The airborne fielder touches the boundary because his last ground contact was not entirely within it.

**Umpire action:** Do not give the batter out. Signal **boundary four**.

---

### Scenario 5: Striking Ball Twice for Runs
**Expected:** Law 34.1 (OUT (Hit the Ball Twice))

**Adjudication Output:**

> **VERDICT: OUT — Hit the ball twice.**

**Law 34.1.1:** The striker is out if, while the ball is in play, it strikes their person or bat and they **wilfully strike it again**. The second hit was made to take a run, not solely to guard the wicket.

**Law 34.3.1** does not apply, because a lawful second hit is permitted only for guarding the wicket, and **no runs may be scored** from such a stroke.

**Umpire action:** Give the batter out using the **Out signal**. The attempted single does not count.

---

### Scenario 6: Ball Beyond Boundary Object
**Expected:** Law 19.4 (YES / BOUNDARY)

**Adjudication Output:**

> **VERDICT: YES — the ball is beyond the boundary.**

**Law:** Law 19.4.1 — the ball is beyond the boundary when it touches “any object that is grounded beyond the boundary.” The advertising board is grounded entirely outside the boundary.

**Umpire Action:** Award the applicable boundary runs under Law 19 and signal **Boundary 4** or **Boundary 6**, as appropriate to the circumstances.

---

### Scenario 7: Batter Leaving Crease During Play
**Expected:** Law 38.1 (OUT (Run Out))

**Adjudication Output:**

> **VERDICT: OUT — Run out.**

Under **Law 38.1.1**, a batter is out if, **at any time while the ball is in play**, they are out of their ground and the fielding side puts down their wicket. Having initially made their ground does not protect the batter after they wander out again before the ball becomes dead.

**Umpire action:** Raise the index finger and signal **OUT**.

---

### Scenario 8: Refusal Test: Wide Ball DRS
**Expected:** Law REFUSAL (CANNOT DETERMINE / REFUSAL)

**Adjudication Output:**

> I cannot determine the ruling based on the official MCC Laws in the corpus.

The supplied context contains no provision governing DRS referrals or challenges to an on-field Wide Ball decision. Therefore, no DRS entitlement or umpire procedure can be established from these clauses.

---

### Scenario 9: Refusal Test: IPL Impact Player
**Expected:** Law REFUSAL (CANNOT DETERMINE / REFUSAL)

**Adjudication Output:**

> I cannot determine the ruling based on the official MCC Laws in the corpus.

The provided context contains no law governing Impact Player substitutions or whether a substitute may bat after an opening batter’s dismissal. Therefore, no definitive verdict or umpire signal can be given under the supplied laws.

---

### Scenario 10: Multiple Hits Solely Guarding Wicket
**Expected:** Law 34.3 (NOT OUT / NO RUNS)

**Adjudication Output:**

> **VERDICT: NOT OUT — NO PENALTY RUNS.**

The striker’s second contact is lawful because the ball was pushed away **solely to guard the wicket**, using the bat held in hand.

- **Law 34.3.1:** The striker may hit the ball a second time with the bat for the sole purpose of guarding their wicket. **No runs may be scored from that stroke.**
- **Law 34.1.1** does not apply because the second strike is permitted under Law 34.3.1.

**Umpire action:** Give no out signal and award no runs. Allow play to continue unless another event makes the ball dead.

---

### Scenario 11: Boundary Airborne Contact
**Expected:** Law 19.5 (BOUNDARY)

**Adjudication Output:**

> **VERDICT: BOUNDARY — the ball is beyond the boundary.**

Under **Law 19.5.1**, the airborne fielder is regarded as grounded beyond the boundary because his last ground contact was beyond it. Under **Law 19.4.2**, an airborne player touches the boundary when his last ground contact was not entirely within the boundary before touching the ball. Therefore, the tap does not keep the ball in play; it is treated as having reached the boundary.

**Umpire action:** Signal **Boundary** and award the applicable boundary allowance—normally **four runs**.

---

### Scenario 12: Ball Hitting Protective Helmet on Turf
**Expected:** Law 28.3 (5 PENALTY RUNS)

**Adjudication Output:**

> **Verdict: 5 penalty runs** to the batting side.

Under **Law 28.3.1**, when the ball in play strikes a protective helmet placed on the ground behind the wicket-keeper, the ball becomes immediately dead and **5 penalty runs are awarded**.

Additionally, under **Law 28.3.2**, any runs completed before the ball struck the helmet, plus the run in progress if the batters had crossed, are also awarded.

**Umpire action:** Signal **Dead Ball** and award **5 penalty runs**, plus any applicable completed or crossed run.

---

### Scenario 13: Non-Striker Stealing Ground
**Expected:** Law 38.3 (OUT (Run Out))

**Adjudication Output:**

> **VERDICT: I cannot determine the ruling based on the official MCC Laws in the corpus.**

The provided context does not define when the ball comes into play. Under **Law 38.3.1**, the non-striker is liable to be Run out only from the moment the ball comes into play until the instant the bowler would normally be expected to release it. If the ball was in play, **Law 38.1.1** would permit a Run out if the non-striker was out of their ground and the wicket was put down.

**Umpire action:** Cannot be specified definitively from the supplied Laws.

---

### Scenario 14: Ball Striking Fielder Grounded Beyond Rope
**Expected:** Law 19.4 (BOUNDARY / 6 RUNS)

**Adjudication Output:**

> **VERDICT: SIX RUNS — boundary signal.**

**Reason:** The fielder’s foot is touching the boundary rope, so the fielder is grounded at/beyond the boundary. The catch is therefore not legal under **Law 19.5.2**. The ball is beyond the boundary under **Law 19.4.1**, as it is in contact with an object—the fielder—grounded at/beyond the boundary.

**Umpire action:** Signal **six runs** by raising both arms above the head.

---

### Scenario 15: Refusal Test: Free Hit No-Ball
**Expected:** Law REFUSAL (CANNOT DETERMINE / REFUSAL)

**Adjudication Output:**

> I cannot determine the ruling based on the official MCC Laws in the corpus.

The provided context contains no provision stating that a front-foot no-ball makes the next delivery a Free Hit. No umpire signal or action can therefore be specified from these clauses.

---
