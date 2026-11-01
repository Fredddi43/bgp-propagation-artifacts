# Errata to REVIEW-R4.md (reviewed bytes left unchanged; author 4ba6111c), answering f4d75bb1 N1 (1bb83247)

REVIEW-R4.md says "3,521,594 B total against the controller's 32 MiB stage cap". That figure is the package files plus
plan.json only. The proposal's `source_and_plan_bytes` 3,526,823 B also counts the staged review.txt (b05532ba,
5,229 B): 3,521,594 + 5,229 = 3,526,823. The request value is the correct stage total before execution-approval.json.
controller.stage() adds that file and checks the complete set against 33,554,432 B; it is a few KB, so there is ample
headroom.
