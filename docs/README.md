# Docs

| File | Purpose |
|------|---------|
| `demo.gif` | Agent flow: route → fixture engine → bounded no-buy answer |
| `eval.md` | Public 20-prompt bare vs skill eval |
| `agent-policy.md` | Response templates + bad/good answers |
| `engine-report.schema.json` | Canonical agent JSON |
| `SOCIAL.md` | Where (and where not) to post |

### Regenerate demo GIF

```bash
cd docs/_lottie_render
npm install puppeteer lottie-web   # once
npm run render                     # writes ../demo.gif (~9s, 960×540)
```

Also ships `demo.lottie.json` (Lottie/Bodymovin JSON — Diffusion Studio–style data-stats
scene). README uses the GIF so GitHub renders without a player.

Inspired by [diffusionstudio/lottie](https://github.com/diffusionstudio/lottie) (motion
taste: calm ease-out, one surface, metric-first beats).
