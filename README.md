# Modelling-for-Transitions
Noah Zuijderwijk
Modelling for Transitions, University of Amsterdam
 October 2026

PyPSA model of the Dutch energy system (2025–2050). This model is an extension of an earlier group assignment in which Rosa Muilu, Sabrina Liu, Sabine Whittman and I looked at how hydrogen production moves from SMR to electrolysis under different gas prices, electrolyser costs and carbon prices. In this individual assignment, I model industrial energy demand more granularly by dividing industrial high-temperature processes into two separate demand segments: one that strictly represents high-temperature processes (e.g. steel-making), and one that represents low-to-medium temperature processes (e.g. food processing). I then carry out a scenario analysis.

## Setup

```bash
conda env create -f group-mt-env.yml
conda activate group-mt-env
```

## Usage

Everything is in `FinalModel/`:

- `interface.ipynb` runs the scenarios and saves them to `results/` as `.nc` files
- `visualisations.ipynb` makes the heatmaps and other figures
- `analysis.ipynb` makes the summary table (`presentation_metrics_summary.csv`)

The model code is in `energy_model/` and the input data (demand, supply, technologies) is in `input_databases/`.

## Scenarios

- Gas price ×1, 3, 5.5, 8 combined with electrolyser CAPEX ×1, 0.75, 0.5, 0.25
- Carbon prices from €0 to €300/t
- A baseline without hydrogen

`OLD/` has earlier versions of the model.
