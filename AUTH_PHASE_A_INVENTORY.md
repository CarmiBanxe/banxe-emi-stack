# Auth Phase A Inventory

## Sources
- api/routers/auth.py
- services/auth/token_manager.py
- services/iam/iam_port.py

## Tasks
- Mark inline JWT encode/decode locations in router
- Mark refresh flow branches
- Mark code that should move behind TokenManagerPort
- Mark IAM calls that should stay behind IAMPort
