# AnalyzeDirStage

## Header
- Stage Name: `AnalyzeDirStage`
- Stage Id: `analyze_dir`
- Previous Stage: `LoopStartStage`
- Start Condition: CLI starts the stage sequence and no prior analysis result is required.
- End Condition: A markdown summary of the target directory is generated and saved to the stage cache.
- On Success: `LoopEndStage`

## Behavior
1. Prompt the user for a directory path.
2. Validate that the path exists and is a directory.
3. If invalid, print an error and prompt again.
4. Run directory analysis with `get_markdown(target_dir, "python-overview")` through `run_with_spinner`.
5. Save the returned markdown text as `{target_dir.name}_{YYYYMMDD}.md` in the stage cache directory.
6. Append the analysis summary to `messages`.
