# LoopStartStage

## Header
- Stage Name: `LoopStartStage`
- Stage Id: `loop_start`
- Previous Stage: `AnalyzeDirStage`
- Start Condition: Directory analysis has completed and an analysis summary is already available in `messages` or stage cache.
- End Condition: The next design target for the loop is selected and a loop-control message is appended to `messages`.
- On Success: `LoopEndStage`

## Behavior
1. Read the current analysis context from `messages`.
2. Determine which file, module, or stage should be handled in the current iteration.
3. Build a short loop-control message that states the current target and the reason it was selected.
4. Append that loop-control message to `messages` as a user message.
5. Return the updated `messages`.
