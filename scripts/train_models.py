"""Run isolated ensemble training/evaluation; never modify production settings."""

from trendforge.cli import evaluate

if __name__ == "__main__":
    evaluate(ensemble=True)
