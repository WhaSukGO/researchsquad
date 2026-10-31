"""Bounded Fashion-MNIST experiment, implementation v1."""
import argparse
import json
import math
import os
import platform
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from safetensors.torch import load_file, save_file
from fashion_model import images, labels
from fashion_study_models import build


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--family', choices=['mlp', 'cnn'], required=True)
    parser.add_argument('--width', type=int, default=16)
    parser.add_argument('--hidden', type=int, default=256)
    parser.add_argument('--dropout', type=float, default=0.2)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--epochs', type=int, default=3)
    parser.add_argument('--batch-size', type=int, default=256)
    args = parser.parse_args()
    assert 1 <= args.epochs <= 5
    output = Path('/workspace/output')
    output.mkdir(parents=True, exist_ok=True)
    log = (output / 'training.jsonl').open('w', buffering=1)

    def emit(value):
        text = json.dumps(value, allow_nan=False)
        print(text, flush=True)
        log.write(text + '\n')

    started = time.perf_counter()
    torch.set_num_threads(4)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required; CPU fallback is forbidden')
    seed = 1337
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device('cuda:0')
    data = Path('/datasets') / args.dataset_id
    x, y = images(data / 'images.gz'), labels(data / 'labels.gz')
    assert x.shape == (60000, 1, 28, 28) and x.dtype == torch.float32
    assert y.shape == (60000,) and y.dtype == torch.int64
    assert bool(torch.isfinite(x).all()) and float(x.min()) >= 0 and float(x.max()) <= 1
    assert int(y.min()) >= 0 and int(y.max()) <= 9
    train_x, valid_x = x[:55000].to(device), x[55000:].to(device)
    train_y, valid_y = y[:55000].to(device), y[55000:].to(device)
    del x, y
    spec = {key: getattr(args, key) for key in ('family', 'width', 'hidden', 'dropout')}
    model = build(spec).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=0)
    order_rng = torch.Generator(device='cpu').manual_seed(seed)
    hyperparameters = {
        'optimizer': 'Adam', 'lr': args.lr, 'weight_decay': 0,
        'betas': [0.9, 0.999], 'eps': 1e-8, 'batch_size': args.batch_size,
        'epochs': args.epochs, 'scheduler': None, 'loss': 'cross_entropy',
        'augmentation': None, 'normalization': 'uint8 / 255',
        'shuffle': 'independent seeded CPU randperm each epoch',
        'drop_last': False, 'checkpoint_selection': 'final epoch only',
        'gradient_clipping': None, 'mixed_precision': False
    }
    environment = {
        'python': platform.python_version(), 'torch': torch.__version__,
        'numpy': np.__version__, 'cuda': torch.version.cuda,
        'cudnn': torch.backends.cudnn.version(), 'gpu': torch.cuda.get_device_name(device),
        'threads': torch.get_num_threads(), 'cudnn_deterministic': True,
        'cudnn_benchmark': False, 'tf32': False,
        'parameter_count': sum(p.numel() for p in model.parameters())
    }
    emit({'event': 'start', 'spec': spec, 'hyperparameters': hyperparameters,
          'environment': environment, 'seed': seed, 'dataset_id': args.dataset_id,
          'train_count': 55000, 'validation_count': 5000})

    def validate(candidate):
        candidate.eval()
        correct = torch.zeros((), device=device, dtype=torch.int64)
        loss_sum = torch.zeros((), device=device, dtype=torch.float64)
        class_count = torch.zeros(10, device=device, dtype=torch.int64)
        class_correct = torch.zeros(10, device=device, dtype=torch.int64)
        with torch.inference_mode():
            for begin in range(0, 5000, args.batch_size):
                target = valid_y[begin:begin + args.batch_size]
                logits = candidate(valid_x[begin:begin + args.batch_size])
                if not bool(torch.isfinite(logits).all()):
                    raise RuntimeError('Nonfinite validation logits')
                matched = logits.argmax(1).eq(target)
                correct += matched.sum()
                loss_sum += F.cross_entropy(logits, target, reduction='sum').double()
                class_count += torch.bincount(target, minlength=10)
                class_correct += torch.bincount(target[matched], minlength=10)
        return {'validation_accuracy': int(correct.item()) / 5000,
                'validation_loss': float(loss_sum.item()) / 5000,
                'validation_correct': int(correct.item()),
                'per_class_correct': class_correct.cpu().tolist(),
                'per_class_count': class_count.cpu().tolist()}

    trajectory = []
    steps = 0
    gradient_checks = 0
    torch.cuda.synchronize()
    training_started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        epoch_started = time.perf_counter()
        model.train()
        order = torch.randperm(55000, generator=order_rng).to(device)
        loss_sum = torch.zeros((), device=device, dtype=torch.float64)
        seen = 0
        for begin in range(0, 55000, args.batch_size):
            indices = order[begin:begin + args.batch_size]
            optimizer.zero_grad(set_to_none=True)
            logits = model(train_x[indices])
            loss = F.cross_entropy(logits, train_y[indices])
            if not bool(torch.isfinite(loss)):
                raise RuntimeError('Nonfinite training loss')
            loss.backward()
            grads = [p.grad for p in model.parameters() if p.requires_grad]
            if any(g is None for g in grads):
                raise RuntimeError('Missing gradient')
            finite = torch.stack([torch.isfinite(g).all() for g in grads]).all()
            gradient_checks += 1
            if not bool(finite):
                emit({'event': 'failure', 'finite_gradients': False, 'step': steps})
                raise RuntimeError('Nonfinite gradient before optimizer update')
            optimizer.step()
            steps += 1
            seen += indices.numel()
            loss_sum += loss.detach().double() * indices.numel()
        assert seen == 55000
        result = validate(model)
        torch.cuda.synchronize()
        row = {'epoch': epoch, 'loss': float(loss_sum.item()) / seen,
               'train_samples_seen': seen, 'optimizer_steps_cumulative': steps,
               'elapsed_seconds': time.perf_counter() - epoch_started, **result}
        assert math.isfinite(row['loss']) and math.isfinite(row['validation_loss'])
        trajectory.append(row)
        emit({'event': 'epoch', **row})
    torch.cuda.synchronize()
    training_elapsed = time.perf_counter() - training_started
    assert steps == args.epochs * math.ceil(55000 / args.batch_size)
    state = {key: value.detach().cpu().contiguous() for key, value in model.state_dict().items()}
    weights_path = output / 'weights.safetensors'
    save_file(state, str(weights_path), metadata={'spec': json.dumps(spec)})
    restored = build(spec).to(device)
    restored.load_state_dict(load_file(str(weights_path)), strict=True)
    reproduced = validate(restored)
    accuracy_delta = abs(reproduced['validation_accuracy'] - trajectory[-1]['validation_accuracy'])
    assert accuracy_delta <= 1e-12
    torch.cuda.synchronize()
    metrics = {
        'implementation_version': 1, 'spec': spec, 'hyperparameters': hyperparameters,
        'seed': seed, 'dataset_id': args.dataset_id,
        'split_counts': {'train': 55000, 'validation': 5000},
        'split_indices': {'train': [0, 55000], 'validation': [55000, 60000], 'end_exclusive': True},
        'per_epoch': trajectory, 'optimizer_steps': steps, 'finite_gradients': True,
        'gradient_checks': gradient_checks,
        'finite_gradient_method': 'All entries of every trainable parameter gradient checked before every optimizer update; abort on missing or nonfinite gradients',
        'device': str(device), 'environment': environment,
        'training_elapsed_seconds': training_elapsed,
        'elapsed_seconds': time.perf_counter() - started,
        'serialization_verification': {'strict_load': True,
                                     'validation_accuracy': reproduced['validation_accuracy'],
                                     'accuracy_delta': accuracy_delta},
        'final_validation_accuracy': trajectory[-1]['validation_accuracy'],
        'official_test_accessed': False, 'resumed': False
    }
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2, allow_nan=False) + '\n')
    (output / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
    emit({'event': 'complete', 'optimizer_steps': steps,
          'final_validation_accuracy': metrics['final_validation_accuracy'],
          'elapsed_seconds': metrics['elapsed_seconds'], 'serialization_verification': metrics['serialization_verification']})
    log.close()


if __name__ == '__main__':
    main()
