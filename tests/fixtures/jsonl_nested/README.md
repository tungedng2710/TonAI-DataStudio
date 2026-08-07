---
license: mit
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train-*.jsonl
      - split: test
        path: data/test.jsonl
---
# Nested support messages

A tiny Hugging Face-compatible fixture with nested metadata and sharded split naming.

