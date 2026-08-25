"""
train_classifier.py
--------------------
Trains InjectionClassifier on deepset/prompt-injections and evaluates
generalization on JailbreakBench.

IMPORTANT: This script needs internet access to huggingface.co to pull the
datasets. It will NOT run inside network-restricted sandboxes (this dev
container included) -- run it on your own machine / Colab / CI runner.

Usage:
    pip install datasets scikit-learn
    python scripts/train_classifier.py

Outputs:
    - models/injection_classifier.pkl   (trained sklearn pipeline)
    - reports/training_metrics.json     (precision/recall/F1 on held-out split)
    - reports/jailbreakbench_eval.json  (out-of-distribution generalization check)
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from safety_checker.injection_classifier import InjectionClassifier


def load_deepset_prompt_injections():
    """
    Loads deepset/prompt-injections from HuggingFace.
    Dataset card: https://huggingface.co/datasets/deepset/prompt-injections
    Fields: 'text' (str), 'label' (0 = benign, 1 = injection)
    Has predefined 'train' and 'test' splits.
    """
    from datasets import load_dataset

    ds = load_dataset("deepset/prompt-injections")
    train_texts = list(ds["train"]["text"])
    train_labels = list(ds["train"]["label"])
    test_texts = list(ds["test"]["text"])
    test_labels = list(ds["test"]["label"])
    return train_texts, train_labels, test_texts, test_labels


def load_jailbreakbench_prompts():
    """
    Loads JailbreakBench harmful-behaviors prompts as an OUT-OF-DISTRIBUTION
    generalization check -- i.e. does a classifier trained only on
    deepset/prompt-injections also catch jailbreak-style attacks it never
    trained on? All examples here are treated as positive (label=1) since
    JailbreakBench prompts are adversarial by construction.

    Dataset card: https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors
    """
    from datasets import load_dataset

    ds = load_dataset("JailbreakBench/JBB-Behaviors", "behaviors")
    # the 'harmful' split contains the goal behaviors used to construct attacks;
    # see the dataset card for exact field names, which can shift between
    # dataset versions -- adjust the key below if HF renames a column.
    split = ds["harmful"] if "harmful" in ds else ds[list(ds.keys())[0]]
    texts = list(split["Goal"]) if "Goal" in split.column_names else list(split[split.column_names[0]])
    labels = [1] * len(texts)
    return texts, labels


def main():
    os.makedirs("models", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    print("Loading deepset/prompt-injections ...")
    train_texts, train_labels, test_texts, test_labels = load_deepset_prompt_injections()
    print(f"  train: {len(train_texts)} examples, test: {len(test_texts)} examples")

    print("Training InjectionClassifier (TF-IDF + LogisticRegression) ...")
    clf = InjectionClassifier()
    # train() does its own internal split for a quick sanity check; then we
    # retrain on ALL of `train` and do the real evaluation on the dataset's
    # own held-out `test` split for a clean, standard-practice number.
    clf.train(train_texts, train_labels, test_size=0.15)

    print("Evaluating on deepset's official test split ...")
    metrics = clf.evaluate(test_texts, test_labels)
    print(json.dumps(metrics, indent=2))
    with open("reports/training_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    clf.save("models/injection_classifier.pkl")
    print("Saved model to models/injection_classifier.pkl")

    print("\nTop features toward 'injection':")
    for feat, weight in clf.top_features(15):
        print(f"  {feat!r}: {weight}")

    # --- Out-of-distribution check against JailbreakBench ---
    try:
        print("\nLoading JailbreakBench for OOD generalization check ...")
        jb_texts, jb_labels = load_jailbreakbench_prompts()
        jb_metrics = clf.evaluate(jb_texts, jb_labels)
        # only recall is meaningful here since every JailbreakBench example is
        # positive by construction -- there's no negative class to measure
        # precision against in this split.
        print(f"JailbreakBench recall (catches attacks unseen during training): "
              f"{jb_metrics['recall']}")
        with open("reports/jailbreakbench_eval.json", "w") as f:
            json.dump(jb_metrics, f, indent=2)
    except Exception as e:
        print(f"Skipping JailbreakBench eval (dataset schema may differ / "
              f"no internet): {e}")


if __name__ == "__main__":
    main()
