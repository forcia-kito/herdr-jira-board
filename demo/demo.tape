# vhs tape for the README demo GIF.
# The interactions are driven externally by demo/drive.sh; this tape only
# attaches a client to the "demo" herdr session and records it.
# Render with:  ./demo/record.sh   (from the repository root)
Output demo/demo.gif

Set FontSize 13
Set Width 1400
Set Height 800
Set Theme "Catppuccin Mocha"
Set Padding 8

Hide
Type "env $(env | grep -oE '^(HERDR|CLAUDE)[A-Z_]*' | sed 's/^/-u /' | tr '\n' ' ') herdr --session demo"
Enter
Sleep 8s
Show

Sleep 175s

Hide
Sleep 5s
