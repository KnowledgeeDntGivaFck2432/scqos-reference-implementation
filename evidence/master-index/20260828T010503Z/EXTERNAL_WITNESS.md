# External Identity and Transparency Witness

The bundle is cryptographically closed without inventing a signer. The real authority may add a public Sigstore witness with:

```bash
cosign sign-blob --yes --bundle SIGSTORE_BUNDLE.json CLOSURE_RECEIPT.json
cosign verify-blob --bundle SIGSTORE_BUNDLE.json CLOSURE_RECEIPT.json
sha256sum SIGSTORE_BUNDLE.json > SIGSTORE_BUNDLE.sha256
```

The Sigstore bundle is additive evidence. It must never replace or rewrite the closed receipt.
