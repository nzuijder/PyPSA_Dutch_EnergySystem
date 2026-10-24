# Modelling-for-Transitions
Noah Zuijderwijk
Modelling for Transitions, University of Amsterdam
 October 2026

PyPSA model of the Dutch energy system (2025–2050). This model is an extension of an earlier group assignment in which Rosa Muilu, Sabrina Liu, Sabine Whittman and I looked at how hydrogen production moves from SMR to electrolysis under different gas prices, water electrolysis CAPEX and carbon prices. In this individual assignment, I model industrial energy demand with more granularity by dividing industrial high-temperature processes into two separate demand segments: one that strictly represents high-temperature processes (e.g. steel-making), and one that represents low-to-medium temperature processes (e.g. food processing). I then carry out a scenario analysis.

## Setup

```bash
conda env create -f group-mt-env.yml
conda activate group-mt-env
```

## Usage

Everything is in `FinalModel/`:

- `interface.ipynb` runs the scenarios and saves them to `results/` as `.nc` files
- `visualisations.ipynb` makes data visualizations

The model code is in `energy_model/` and the input data (demand, supply, technologies) is in `input_databases/`.

## Scenarios

- A baseline without applied multipliers
- Large-scale heat pump CAPEX ×1, 0.93, 0.87, 0.80 combined with efficiency ×1, 1.04, 1.08, 1.12
- Carbon price x1, 4, 8, 12
- Large-scale heat pump CAPEX ×1, 0.93, 0.87, 0.80 combined with efficiency ×1, 1.04, 1.08, 1.12 AND Carbon price x1, 4, 8, 12

`OLD/` has earlier versions of the model.
