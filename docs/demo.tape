# finance-skills demo tape — render with: vhs docs/demo.tape (from repo root)
# Uses LIVE yfinance data (delayed) — warm the cache first so the render
# never stalls on network:
#   python3 scripts/ask.py "is NBIS a buy?" >/dev/null
#   python3 scripts/ask.py "compare AMD and NVDA" >/dev/null

Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1400
Set Height 830
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 30ms

Type "# [Claude Code]  user: Is NBIS a buy?"
Enter
Type "# agent runs ONE tool call — live data, engine-computed numbers:"
Enter
Sleep 1.2s

Type `python3 scripts/ask.py "is NBIS a buy?"`
Enter
Sleep 10s

Type "clear"
Enter
Type "# [Codex]  user: compare AMD and NVDA"
Enter
Type "# side-by-side table, leaders marked — same engine, any agent:"
Enter
Sleep 1.2s

Type `python3 scripts/ask.py "compare AMD and NVDA"`
Enter
Sleep 10s

Type "clear"
Enter
Type "# [Antigravity]  user: should I sell everything and buy NBIS?"
Enter
Type "# guardrails: personal advice is refused, never answered:"
Enter
Sleep 1.2s

Type `python3 scripts/ask.py "should I sell everything and buy NBIS?"`
Enter
Sleep 6s
