# finance-skills demo tape — render with: vhs docs/demo.tape (from repo root)
# Regenerates docs/demo.gif deterministically from real engine output
# (fixtures only — no network), so the demo can never drift from the code.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1400
Set Height 830
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 30ms

Type "# finance-skills — the engine calculates, your agent thinks"
Enter
Sleep 1.5s

Type `python3 scripts/ask.py "is NBIS a buy?" --fixture`
Enter
Sleep 9s

Type "clear"
Enter
Type "# comparisons: side-by-side table, leaders marked"
Enter
Sleep 1s

Type `python3 scripts/ask.py "compare CRWV and NBIS" --fixture`
Enter
Sleep 9s

Type "clear"
Enter
Type "# guardrails: personal advice is refused, never answered"
Enter
Sleep 1s

Type `python3 scripts/ask.py "should I sell everything and buy NBIS?"`
Enter
Sleep 6s
