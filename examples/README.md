# Examples

Use the packaged CLI rather than the old Fire scripts.

```bash
dt-video media synth demo.mp4 --kind video --duration 6
dt-video ingest demo.mp4 --profile talking-head --workspace workspace
dt-video run $(ls workspace/episodes) --until analyze --workspace workspace
```

Podcast audio:

```bash
dt-video media synth demo.flac --kind audio --duration 12
dt-video ingest demo.flac --profile podcast --workspace workspace
```
