# Validation

Run the automated suite and static checks from a Python 3.12 environment:

```powershell
uv run --frozen pytest -q
uv run --frozen ruff check src tests tools
```

Tests use temporary databases and generic synthetic fixtures. Coverage includes tool authorization, exact-context cloud approval, cancellation, provider isolation, browser capture validation, microphone conditioning, transcript review, voice queue ordering, interface loading, and configuration.

Optional packaged checks:

```powershell
Macooii.exe --data-dir temporary-test-directory --smoke-test --screenshot interface.png
Macooii.exe --verify-neural-voice voice-report.json
Macooii.exe --verify-voice-order order-report.json
Macooii.exe --verify-response-speed latency-report.json
```

Voice checks play public synthetic sentences. The action-order check uses a disposable note. The response-speed check uses synthetic English input and a fixed public reply without microphone capture, cloud calls, or executing the spoken example command. Models must already be installed. Generated reports and screenshots stay outside version control.

Real microphone accuracy, language mixing, physical speaker output, shortcuts shared with other apps, browser account selection, and website autoplay require interactive verification. Measurements vary by hardware, selected models, and network. Synthetic checks do not establish a real-user accuracy rate or performance guarantee.
