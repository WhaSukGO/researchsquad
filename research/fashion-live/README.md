# Actual-agent Fashion-MNIST study

`train.py` preserves the original training program authored by the live Engineering
agent, not the prior scripted fixture. The study selected an MLP baseline and a CNN
comparison, inspected baseline feedback, then chose the corresponding architecture
change. Both used seed 1337, Adam 0.001, batch 256 and 3 epochs, with 55,000 train /
5,000 validation samples. Final validation: 86.74% and 88.06%; selected CNN protected
test: 87.55% on 10,000 examples, evaluated once after selection and reviews.

Replay this saved trainer through `start_job`, not host execution. Include this
file and `goalagent/fashion_model.py`, `goalagent/fashion_study_models.py` as frozen
code files. The entrypoint accepts `--dataset-id ID --family mlp|cnn --width 16
--hidden 256 --dropout 0.2 --lr 0.001 --epochs 3 --batch-size 256`. Register only the
official train files as images.gz/labels.gz and use the approved CUDA profile.
Do not hand official test data to training jobs.

To run a fresh actual-agent study (whose choices may differ):

```sh
python -m goalagent.fashion_live --run-dir tmp/NEW-LIVE-STUDY
```

This consumes real provider calls. It uses the common Agent and default Codex
provider, not scripted choices. A reviewed declarative MLP/CNN registry bounds model
selection so the independent evaluator never imports agent Python. The runner
protects a single final test selection. A valid study is not a promised accuracy.

Full role rationale, errors and limitations:
`docs/verification/fashion-live-20261030.json`. Raw traces/data/weights stay local.
