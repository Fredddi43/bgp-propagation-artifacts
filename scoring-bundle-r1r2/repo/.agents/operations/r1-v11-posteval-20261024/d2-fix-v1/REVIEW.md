# d2 fix: recorded('d0') follows the d0-readback rule

The reviewed d2.recorded('d0') returns the executed D0 record's output_sha256 `{"cells":` (exec skipped the sha line), so
D2 would refuse on the D0/D1 capture sha mismatch. d2_r2 changes only recorded() (function-AST diff = ['recorded']):
the same rule and 64-hex validation as phases_r2 (approved b96c4c6f). On the actual records it returns the executed
readback plan sha 6e18854b and D1 census 7b746087. DEST, code shas and phase records are unchanged; run-records are
fresh in this directory. 3 tests pass.
