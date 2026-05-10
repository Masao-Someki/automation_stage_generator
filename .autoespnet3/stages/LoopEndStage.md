# LoopEndStage

## Header
- Stage Name: `LoopEndStage`
- Stage Id: `loop_end`
- Previous Stage: `LoopStartStage`
- Start Condition: One loop iteration has finished and its result has been added to `messages` or saved in stage cache.
- End Condition: At least one markdown exists under `.autoespnet3/cache/AnalyzeDirStage/`.
- On Success: `End`
- On Incomplete: `LoopStartStage`

## Behavior
1. Check whether any markdown file exists at `.autoespnet3/cache/AnalyzeDirStage/*.md`.
2. If at least one markdown exists, mark this iteration as complete and continue via `On Success`.
3. If no markdown exists, mark this iteration as incomplete and continue via `On Incomplete`.
4. Optionally append a short status message to `messages` describing the decision.
5. Return the updated `messages`.
