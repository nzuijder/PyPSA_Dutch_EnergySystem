"""Post-processing to calculate annual net emissions and direct industrial gas-boiler emissions. 
Cumulative emissions were estimated using trapezoidal integration between modeled years, assuming 
linear changes in annual emission rates and setting cumulative emissions to zero in the first modeled year."""

import numpy as np
import pandas as pd
import pypsa


def annual_emissions(n):
    """Annual net system and industrial LTP boiler emissions, in MtCO₂/year."""
    atmospheric_links = n.links.index[
        n.links.bus2.eq("CO2 atmosphere")
    ]

    boilers = n.links.index[
        n.links.bus0.eq("Gas supply")
        & n.links.bus1.eq("Industrial LTP")
        & n.links.bus2.eq("CO2 atmosphere")
    ]

    # Negative p2 means injection into the atmospheric bus.
    # Retain negative emissions, including modeled BECCS removals.
    emissions = -n.links_t.p2[atmospheric_links]

    rates = pd.DataFrame({
        "System": emissions.sum(axis=1),
        "Gas boilers": emissions[boilers].sum(axis=1),
    })

    return (
        rates.mul(n.snapshot_weightings["generators"], axis=0)
        .groupby(level=0)
        .sum()
        / 1e6
    )


def integrate_annual_rates(annual):
    """Trapezoidal integration, with zero cumulative emissions initially."""
    annual = annual.sort_index()
    years = annual.index.to_numpy(dtype=float)
    rates = annual.to_numpy(dtype=float)

    increments = (
        0.5 * (rates[:-1] + rates[1:])
        * np.diff(years)[:, None]
    )
    cumulative = np.vstack([
        np.zeros((1, rates.shape[1])),
        np.cumsum(increments, axis=0),
    ])

    return pd.DataFrame(
        cumulative, index=annual.index, columns=annual.columns
    )

