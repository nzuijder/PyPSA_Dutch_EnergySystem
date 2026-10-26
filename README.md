# industrial-heat-pypsa
Noah Zuijderwijk
Modelling for Transitions, University of Amsterdam
 October 2026

This repository contains a PyPSA model of the Dutch energy system, used to explore how heat pump investment subsidies and carbon pricing influence industrial heat electrification and decarbonisation between 2020 and 2050. The model builds on an earlier group assignment with Rosa Muilu, Sabrina Liu and Sabine Whittman. That project examined the transition from steam methane reforming (SMR) to water electrolysis for hydrogen production under different assumptions about gas prices, electrolyser capital costs and carbon prices. In this individual extension, I represent industrial heat demand in greater detail by splitting the original high-temperature demand category into two segments: high-temperature processes, such as steelmaking, and low-to-medium-temperature processes, such as food processing. I then use scenario analysis to examine how heat pump investment subsidies and carbon pricing affect technology investment and the supply of industrial heat.

## Final report

The final report, containing model assumptions, limitations, and main takeaways is included as "Final_report.pdf"

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
