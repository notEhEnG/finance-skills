# Docs

| File | Purpose |
|------|---------|
| `demo.gif` | VHS-rendered agent sessions using the real one-shot path |
| `demo.tape` | Reproducible VHS source for `demo.gif` |
| `demo-agent.gif` / `.mp4` | Full Claude Code session capture |
| `eval.md` | Public 20-prompt bare vs skill eval |
| `agent-policy.md` | Response templates + bad/good answers |
| `engine-report.schema.json` | Canonical agent JSON |
| `SOCIAL.md` | Where (and where not) to post |

### Regenerate demo GIF with VHS

```bash
vhs docs/demo.tape
```

The `demo` GitHub workflow performs the same render when the tape or answer path
changes. The retired Lottie renderer is not part of the repository.
