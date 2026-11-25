"""Refine a human-reviewed binary head on its native, frozen visual embeddings."""
from dataclasses import dataclass
from math import log

import numpy as np
import torch
from torch.nn import functional as F


@dataclass(frozen=True)
class Recipe:
    epochs: int = 36
    learning_rate: float = 0.00015
    star_weight: float = 5.0
    pin_weight: float = 12.0
    threshold: float = 0.60
    seed: int = 731


@torch.no_grad()
def logits(head, embeddings):
    head.eval()
    parts = []
    for batch in embeddings.split(1024):
        scores = head(batch)
        parts.append(scores[:, 0] - scores[:, 1])
    return torch.cat(parts)


def fit(head, embeddings, targets, importance, recipe, observe=None):
    """Mine difficult normals anew each epoch and mix them with uniform negatives.

    Class-stratified batches preserve scarce anomalous examples. Reviewer importance
    weights the per-example loss, including hard positives already near the boundary.
    """
    torch.manual_seed(recipe.seed)
    rng = np.random.default_rng(recipe.seed)
    positive = np.flatnonzero(targets.numpy())
    negative = np.flatnonzero(~targets.numpy())
    if not len(positive) or not len(negative):
        raise ValueError("Both human-reviewed classes are required")
    if len(embeddings) != len(targets) or len(importance) != len(targets):
        raise ValueError("Embedding, target and importance counts differ")
    if not torch.isfinite(importance).all() or (importance <= 0).any():
        raise ValueError("Review importance must be positive and finite")
    optimizer = torch.optim.AdamW(head.parameters(), lr=recipe.learning_rate)
    boundary = log(recipe.threshold / (1 - recipe.threshold))
    hard_count = min(len(negative), 4 * len(positive))
    for epoch in range(1, recipe.epochs + 1):
        margins = logits(head, embeddings)[negative].numpy()
        hardest = negative[np.argpartition(margins, -hard_count)[-hard_count:]]
        # Distinct sources of negative evidence: confusions and ordinary sky.
        ordinary = rng.choice(negative, size=hard_count, replace=False)
        indices = rng.permutation(np.concatenate((positive, hardest, ordinary)))
        # Optimize the deployed deterministic head, without dropout noise.
        for offset in range(0, len(indices), 256):
            idx = indices[offset:offset + 256]
            score = head(embeddings[idx])
            margin = score[:, 0] - score[:, 1] - boundary
            signed = torch.where(targets[idx], margin, -margin)
            loss = (importance[idx] * F.softplus(0.8 - signed)).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        if observe:
            observe(epoch, head)
    return head.eval()
