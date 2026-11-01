# Revision2 — receipt discriminator fix only

The original receipt dict placed its desired kind before **metadata_derivation, which overwrote it. This revision places `kind:r1_metadata_derivation_receipt_v1` after the inherited fields. An explicit assertion now proves that exact kind. Every spec/seal/ledger/scientific-policy byte and transformation remains unchanged. 24 tests passed in4.59s. Prior independently reviewed packet and requirements apply. No execution approval or actual successor artifacts generated.
