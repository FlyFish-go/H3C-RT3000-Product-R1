# RC1 qca-ssdk binary pinning

`qca-ssdk.ko` embeds a `__DATE__`/`__TIME__` string, so its SHA256 is not
source-build reproducible: rebuilding the same unmodified source yields a
different hash while shipping identical code.

Product R1 RC1 therefore **pins** the module to the byte-exact binary that was
hardware-accepted as part of the R1-NET-D network baseline:

```
sha256 : d493b3bddbdf6c0fb9b1a8ae576d4e47b23881671c8737f4341816a0a20c6497
size   : 544716
source : the canonical product-r1-prerelease-1.ubi artifact
         (artifact sha256 162d84ae74528bbee19f46e0079a3c86a4c88b935fd9679a01b83fe63fdedf8c)
```

Semantics: this hash identifies the **hardware-accepted QCA-SSDK binary
baseline**. It does not mean "the same source always rebuilds to this hash".

This is binary pinning for the release, not a source modification. The qca-ssdk
source and its patches are untouched, and no build flag is changed.
