# TODO — A.3 (mypy barrier)

- [x] Read current CI workflow and mypy config
- [x] Run mypy on target scope (brain/core, brain/cognition) to capture current errors
- [x] Prepare focused fix plan for critical type issues
- [ ] Apply code fixes for mypy errors
- [ ] Update CI workflow: remove `|| true` from mypy step
- [ ] Re-run mypy target scope and confirm clean (or documented minimal ignores)
- [ ] Re-run regression tests
- [ ] Summarize A.3 completion

## Current mypy findings
- brain/core/contracts.py: ContractMixin uses dataclasses.asdict/fields but base class is not a dataclass type (3 errors)
- brain/cognition/goal_manager.py: potential None access in status()["current_goal"]
- brain/cognition/cognitive_core.py: returning Any where Dict[str, Any] expected (metadata flow)
