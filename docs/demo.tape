# finance-skills demo tape — render with: vhs docs/demo.tape (from repo root)
# Frames the terminal as an agent session: a hidden command_not_found_handle
# routes the typed question straight into scripts/ask.py, so the gif shows
# only the agent prompt + engine output (no python plumbing).
#
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
Set TypingSpeed 45ms

Hide
Type `command_not_found_handle() { python3 scripts/ask.py "$*"; }; export PS1="[Claude Code] ❯ "; clear`
Enter
Show

Sleep 1s
Type "Is NBIS a buy?"
Sleep 500ms
Enter
Sleep 10s

Hide
Type `export PS1="[Codex] ❯ "; clear`
Enter
Show

Sleep 1s
Type "compare AMD and NVDA"
Sleep 500ms
Enter
Sleep 10s

Hide
Type `export PS1="[Antigravity] ❯ "; clear`
Enter
Show

Sleep 1s
Type "should I sell everything and buy NBIS?"
Sleep 500ms
Enter
Sleep 6s
