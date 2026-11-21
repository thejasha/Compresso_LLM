# Compresso Evaluation Project

Evaluate the Compresso compression method on LLM memory data (CPU-based LLM) and on GEM5 simulations.

**Final deadline: December 15th**

## Project Workflow

```mermaid
flowchart TD
    A[Study Compresso] --> B[Implement Compresso]
    C[Set up CPU LLM] --> D[Collect LLM Memory Data]
    E[Set up GEM5]

    B --> F[Test Compresso on LLM]
    D --> F
    E --> G[Test Compresso on GEM5]
    F --> G

    F --> H[Eval Compresso on LLM]
    G --> I[Eval Compresso on GEM5]

    H --> J[Final Report & Final Presentation]
    I --> J
```

## Hardware (gem5)

On the laptop's Ubuntu or a CAE Linux machine, from this repo:

```bash
bash sim/setup.sh
bash sim/run-hello.sh
```

`sim/setup.sh` downloads and builds gem5 on that machine. The source is not committed. Details are in `sim/README.md`.
