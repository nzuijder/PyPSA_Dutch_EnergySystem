"""Build and solve the PyPSA energy model."""

import numpy as np
import pandas as pd
import pypsa

# Logging to control running log output
import logging
logging.getLogger("pypsa").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)
logging.getLogger("gurobipy").setLevel(logging.ERROR)

from .preprocessing import (
    preprocess_demand,
    preprocess_supply,
    preprocess_technologies,
    int_extrapolate
)

# ============================================================
# MODEL HELPER FUNCTIONS
# ============================================================

def annuity(disc_rate, life):
    return disc_rate / (1.0 - 1.0 / (1.0 + disc_rate) ** life)

def investment_cost(technology, year, techs_d, rt): 
    capex = techs_d.at[(technology,'CAPEX'),year] 
    fom = techs_d.at[(technology,'FOM'),year] 
    lt = techs_d.at[(technology,'Lifetime'),year]
    return (capex*annuity(rt, lt) + fom) # (€/activity output unit) 


def techs_by_type(techs_s, t): 
    """Retrieve a list with all techs of type t (e.g link, generator, etc.)"""
    types = techs_s.query("Parameter=='Type'").reset_index()
    return list(types[types['Value']==t]['Technology'].unique())
    
#     - ```def get_topology(t)```: 
def get_topology(techs_s, technology):
    """returns a df with the inputs and outputs of technology, with t's buses as index"""
    techdf = techs_s.loc[(technology,slice(None)),:].reset_index()
    techdf = techdf[techdf.Parameter.str.startswith('bus')].set_index('Parameter')
    return techdf

#     - ```def start_year(t)```: 
def start_year(techs_s, technology, years): 
    """if a start-year is specified returns it, otherwise default to years[0]"""
    try: 
        sy = techs_s.at[(technology,'Start year'),'Value']
    except KeyError:
        sy = years[0]
    return sy

def get_cap_constraints(t, years, cn):
    """
    Returns a df with any user-defined constraints (cn) on capacity for tech t. 
    The base year is only used to set up fixed capacity bounds. This is not extrapolated to future years.
    Any min/max constraints set for future years are inter/extrapolated. 
    Returns a NaN df if there are no constraints for t. 
    """

    # Set up empty df
    df = pd.DataFrame(columns=['Technology','Type']+years)
    df.Technology = [t] * 2
    df.Type = ['min','max']
    df = df.set_index(['Technology','Type'])

    # Fill it with user-defined constraints from the technologies input table
    df.loc[:,:] = cn.loc[:,:]

    # The base year is only used to set up fixed capacity bounds, we don't want to extrapolate those to future years. 
    # We only want to int/extrapolate if there are user-constraints on max or min cap limits after the base year:
    # Slice df for years > base year, and store index of non-nan values
    df_idx = df.loc[:,[y for y in years if ((y>years[0]) and (y in df.columns))]]
    idx = np.where(df_idx.notna())

    # If there are no non-nan values, return df as it is:
    if len(df_idx.iloc[idx[0],idx[1]])==0:
        ret = df

    # otherwise int-extrapolate:
    else:
        ret = int_extrapolate(df, years)            

    return ret

# ============================================================
# MAIN MODEL FUNCTION
# ============================================================

def model_run(db_dir, years, t_res, passenger_cars_cf, rt, rs):
    """
    Build and solve the energy model.

    Parameters
    ----------
    db_dir
        Folder containing the input database.
    years
        Model periods.
    t_res
        Intra-year temporal resolution.
    passenger_cars_cf
        Conversion factor for passenger cars.
    rt
        Technical discount rate.
    rs
        Social discount rate.

    Returns
    -------
    pypsa.Network
        The optimized PyPSA network.
    """

    # --------------------------
    # 1. PREPROCESS INPUT DATA
    # --------------------------

    # Call the preprocessing functions and store their outputs.
    
    demands, demand_profiles_prj = preprocess_demand(
            db_dir, years, t_res
        )
    resources, resources_pars, ren_profiles = preprocess_supply(
            db_dir, years, t_res
        )

    techs_s, techs_d, cn = preprocess_technologies(
            db_dir, years, passenger_cars_cf
        )
    # --------------------------
    # 2. CREATE PYPSA NETWORK
    # --------------------------

    # Create the network and define snapshots/model periods.

    n = pypsa.Network()

    # Define snapshots and investment periods from demand profiles index:
    n.set_snapshots(demand_profiles_prj.index, 
                    default_snapshot_weightings=t_res)

    n.investment_periods = years

    # Set the legth of each period:
    n.investment_period_weightings['years'] = list(np.diff(years)) + [list(np.diff(years))[-1]] # the last period gets the same delta as the second last

    # Set the weight of each period on the objective function.
    # For this we use a "social" discount rate rs=1% 
    # (lower than the "technical" discout rate rt used for annuitization):
    T = 0
    for period, nyears in n.investment_period_weightings.years.items():
        discounts = [(1 / (1 + rs) ** t) for t in range(T, T + nyears)]
        n.investment_period_weightings.at[period, 'objective'] = sum(discounts)
        T += nyears

    

    # --------------------------
    # 3. ADD MODEL COMPONENTS
    # --------------------------

    # From the demand dataframes: add all buses and corresponding loads
    
    # Add demand buses and corresponding carrier
    for b in demands.Bus.unique():
        n.add("Bus", b, carrier=demands[demands.Bus==b]['Carrier'].values[0])

    # Add loads, with the right demand bus from the demands dataframe
    # and the right profile from the demand_profiles_prj dataframe
    for d in demands.index:
        n.add("Load", d, 
            bus=demands.at[d,'Bus'], 
            p_set=demand_profiles_prj.loc[:,d].values)

    # From the resources dataframe: Loop over all resources and distinguish three separate cases
    #     - For Secondary resources add a bus
    #     - For Reserves add a bus and a store
    #     - For Emissions add a bus, a store and a maximum limit

    for s in resources['Resource'].unique():

        # for secondary resources add a bus
        if resources[resources.Resource==s]['Type'].values[0] == 'Secondary':
            n.add("Bus", s, carrier = resources[resources.Resource==s]['Carrier'].values[0])

        #  for reserves add a bus...
        elif resources[resources.Resource==s]['Type'].values[0] == 'Reserve':
            n.add("Bus", s, carrier=resources[resources.Resource==s]['Carrier'].values[0])
                    
            # ... and a store
            n.add(
                "Store",
                s,
                carrier = resources[resources.Resource==s]['Carrier'].values[0],
                bus = s,
                # Max energy in the store at any given time:
                e_nom = resources_pars[(resources_pars.Resource==s) & (resources_pars.Parameter=='Reserves')][years[0]].values[0],
                # Initial energy in the store (it's a reserve, so we set it equal to e_nom)
                e_initial = resources_pars[(resources_pars.Resource==s) & (resources_pars.Parameter=='Reserves')][years[0]].values[0],
                # Whether the model can optimize e_nom
                e_nom_extendable = False,
                # Whether the stored energy has to return to e_initial at the end of a period
                e_cyclic = False,
                )
        
        # For emissions add a bus...
        elif resources[resources.Resource==s]['Type'].values[0] == 'Emissions':
            n.add("Bus", s, carrier=resources[resources.Resource==s]['Carrier'].values[0])
            
            # ... an upper value to limit maximum cumulated emissions at any snapshot within a given year...
            co2_max_profile = pd.Series(index=n.snapshots, dtype=float)
            for y in years:
                co2_max_profile.loc[y] = resources_pars[(resources_pars.Resource==s) &\
                                                        (resources_pars.Parameter=='Budget')][y].values[0]

            # ... and a store
            n.add(
                "Store",
                s,
                carrier=resources[resources.Resource==s]['Carrier'].values[0],
                bus=s,
                # For CO2 we add e_nom as a normalized value...
                e_nom=1,
                # ... and then we set the yearly max cumulated emissions relative to e_nom
                e_max_pu = co2_max_profile, 
                e_initial=0,
                e_nom_extendable=False,
                e_cyclic=False,
                )

            
    # Loop over periods to add all technologies, distinguishing three separate cases:
    #     - Generators - loop through all generators and add them to the network
    #     - Links - loop over all links, check type of link (nr of inputs and outputs), and add to the network
    #     - Storage Units - loop over all storage units and add them to the network


    # Loop over model years to add all technologies:
    for y in years:
        print(y)

        # We use techs_by_type to distinguish generators, links and storage units

        # Generators:
        for t in techs_by_type(techs_s, 'Generator'):
            # Add capacity constraints
            cap_constraints = get_cap_constraints(t,years,cn)
            bus0 = techs_s.at[(t,'bus0'), 'Value'] # bus0 as carrier
            bus1 = techs_s.at[(t,'bus1'), 'Value'] # bus1 as bus

            n.add(
                'Generator',
                f'{t}_{y}',
                carrier = bus0,
                bus = bus1,
                p_nom_extendable = True,
                p_max_pu = ren_profiles[bus0].values, # apply renewable profiles as max availability factors
                build_year = max([start_year(techs_s,t,years),y]),  # make sure t won't be built before its start_year
                capital_cost = investment_cost(t, y, techs_d, rt),
                marginal_cost = techs_d.at[(t,'VOM'),y],
                lifetime = techs_d.at[(t,'Lifetime'),y],
                efficiency = techs_d.at[(t,'Efficiency'),y],
                p_nom_max = cap_constraints.at[(t,'max'),y],
                p_nom_min = cap_constraints.at[(t,'min'),y],
                )
        
        # Links:
        for t in techs_by_type(techs_s,'Link'):
             if (('existing' in t) and (y>years[0])):  # if t is labeled as "existing" and the current year in the loop (y) is not the base year,
                    continue                              # move on to the next technology
             else:                                     # if t is not "existing" or y = base year add t to the model with the usual code
                    
                    # rest of the link code block here
                # First, get the link topology dataframe
                topology = get_topology(techs_s, t)

                # Retrieve the capacity constraints
                cap_constraints = get_cap_constraints(t,years,cn)

                # Second, check if a cost is specified for any of the buses in the link
                bus_cost = {}
                for b in topology.index:
                    try:
                        bus_cost[b] = resources_pars[(resources_pars.Resource==topology.at[b,'Value']) &\
                                                    (resources_pars.Parameter=='Price')][y].values[0]
                    # In case there are no costs specified and an error is raised, set the costs to 0:
                    except IndexError:
                        bus_cost[b] = 0 
                    except KeyError:
                        bus_cost[b] = 0 

                # 1. Simple link, one input one output (two  buses)
                if len(topology)==2:
                    n.add(
                        'Link',
                        f'{t}_{y}',
                        carrier = t, # for links we will use the technology name as carrier (it helps sorting out the results)
                        bus0 = topology.at['bus0','Value'], # input bus
                        bus1 = topology.at['bus1','Value'], # output bus
                        p_nom_extendable = True,
                        build_year = max([start_year(techs_s,t,years),y]),
                        capital_cost = investment_cost(t, y, techs_d, rt) * techs_d.at[(t,'Efficiency'), y], # for links costs are expressed in €/activity unit input
                        marginal_cost = techs_d.at[(t,'VOM'), y] + bus_cost['bus0'] + bus_cost['bus1']*techs_d.at[(t,'Efficiency'), y], # VOM + any costs associated with the inputs or the outputs
                        lifetime = techs_d.at[(t,'Lifetime'), y],
                        efficiency = techs_d.at[(t,'Efficiency'), y],
                        p_nom_max = cap_constraints.at[(t,'max'),y] / techs_d.at[(t,'Efficiency'), y],
                        p_nom_min = cap_constraints.at[(t,'min'),y] / techs_d.at[(t,'Efficiency'), y],
                        )
                    
                # 2. Link with three buses (e.g. links with emissions)
                elif len(topology)==3:
                    # Such a link will have two efficiencies:
                    eff1 = techs_d.at[(t,'Efficiency'), y]
                    eff2 = techs_d.at[(t,topology.at['bus2','Efficiency_link']), y]

                    n.add(
                        'Link',
                        f'{t}_{y}',
                        carrier = t, 
                        bus0 = topology.at['bus0','Value'],
                        bus1 = topology.at['bus1','Value'],
                        bus2 = topology.at['bus2','Value'],
                        p_nom_extendable = True,
                        build_year = max([start_year(techs_s,t,years),y]),
                        capital_cost = investment_cost(t, y, techs_d, rt) * techs_d.at[(t,'Efficiency'), y], 
                        marginal_cost = techs_d.at[(t,'VOM'), y] + bus_cost['bus0'] + bus_cost['bus1']*eff1 + bus_cost['bus2']*eff2,
                        lifetime = techs_d.at[(t,'Lifetime'), y],
                        efficiency = eff1,
                        efficiency2 = eff2,
                        p_nom_max = cap_constraints.at[(t,'max'),y] / techs_d.at[(t,'Efficiency'), y],
                        p_nom_min = cap_constraints.at[(t,'min'),y] / techs_d.at[(t,'Efficiency'), y],
                        )
                
                # 3. Link with four buses (e.g. CCS technologies)
                elif len(topology) == 4:
                    # Main output efficiency
                    eff1 = techs_d.at[(t, 'Efficiency'), y]
                    # Emissions released to the atmosphere
                    eff2 = techs_d.at[
                        (t, topology.at['bus2', 'Efficiency_link']), y
                    ]
                    # Emissions captured and stored
                    eff3 = techs_d.at[
                        (t, topology.at['bus3', 'Efficiency_link']), y
                    ]

                    n.add(
                        'Link',
                        f'{t}_{y}',
                        carrier=t,
                        bus0=topology.at['bus0', 'Value'],
                        bus1=topology.at['bus1', 'Value'],
                        bus2=topology.at['bus2', 'Value'],
                        bus3=topology.at['bus3', 'Value'],
                        p_nom_extendable=True,
                        build_year=max([start_year(techs_s, t, years), y]),
                        capital_cost=(
                            investment_cost(t, y, techs_d, rt)
                            * techs_d.at[(t, 'Efficiency'), y]
                        ),
                        marginal_cost=(
                            techs_d.at[(t, 'VOM'), y]
                            + bus_cost['bus0']
                            + bus_cost['bus1'] * eff1
                            + bus_cost['bus2'] * eff2
                            + bus_cost['bus3'] * eff3
                        ),
                        lifetime=techs_d.at[(t, 'Lifetime'), y],
                        efficiency=eff1,
                        efficiency2=eff2,
                        efficiency3=eff3,
                        p_nom_max = cap_constraints.at[(t,'max'),y] / techs_d.at[(t,'Efficiency'), y],
                        p_nom_min = cap_constraints.at[(t,'min'),y] / techs_d.at[(t,'Efficiency'), y],
                    )

        # StorageUnits
        for t in techs_by_type(techs_s,'StorageUnit'):
            n.add(
                'StorageUnit',
                f'{t}_{y}',
                bus = techs_s.at[(t,'bus0'), 'Value'],
                carrier = t,
                capital_cost = investment_cost(t,y,techs_d,rt),
                efficiency_store = techs_d.at[(t,'Efficiency'), y],
                efficiency_dispatch = techs_d.at[(t,'Efficiency'), y],
                build_year = max([start_year(techs_s,t,years),y]),
                p_nom_extendable=True,
                cyclic_state_of_charge=True,
            )

    # --------------------------
    # 4. SOLVE MODEL
    # --------------------------

    n.sanitize()
    
    status, condition = n.optimize(multi_investment_periods=True, 
            solver_name='gurobi',
            log_to_console=False,
            include_objective_constant=False, 
            solver_options={
                "LogFile": "results//solver_run.log",
                "LogToConsole": 0,
                "TimeLimit": 43200
                }
            )

    print("\n")
    print(f"Model Status: {status}")
    print(f"Termination Condition: {condition}")
    print(f"Objective value: {n.objective}")
    
    return n
