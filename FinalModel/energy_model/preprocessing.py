"""Preprocess the Excel input data before building the PyPSA model."""

import pandas as pd


def int_extrapolate(df, model_years):
    """Interpolate and extrapolate numeric year columns."""
    num_cols = [c for c in df.columns if str(c).isnumeric()]
    # make sure numerical columns are treated as floats
    df = df.astype({c: float for c in num_cols})

    # merge num_cols and model years, sort and strip duplicates 
    cols = sorted(list(set(num_cols + model_years)))
    
    # create temporary df with the same index and all model years
    df_temp = pd.DataFrame(index=df.index,
                            columns=pd.Index(cols).drop_duplicates()).astype(float)
    
    # fill it with the existing data
    df_temp.loc[:,[c for c in num_cols]] = df.loc[:,[c for c in num_cols]]
    # Inter/extrapolate parameters in missing model years (if any)
    df_temp.interpolate(method='index',axis=1,inplace=True)
    
    # Use the temporary df to add parameters for missing years (if any), and reorder columns
    df.loc[:,model_years] = df_temp.loc[:,model_years]
    df = df[[c for c in df.columns if c not in cols] + model_years]

    return df


def propagate_profiles(df, model_years, t_res):
    """Resample a profile and propagate it to all model years."""
    df = df.resample(f'{t_res}h').mean()
    
    # store temporal info in separate columns
    df['year'] = df.index.year
    df['month'] = df.index.month
    df['day'] = df.index.day
    df['hour'] = df.index.hour
    
    # create a bucket-list for propagated profiles
    profiles_prjs = []
    # loop over model_years and fill the list
    for y in model_years:
        # reset original index
        df = df.reset_index(drop=True)
        # change year to y 
        # (this is how the original profile gets propageted to all model years!)
        df['year'] = y
        # create a new date-time index with the new year and the rest of the original temporal info
        df['new_idx'] = df.year.astype(str) + '-' + df.month.astype(str) + '-' + df.day.astype(str) + ' ' + df.hour.astype(str) + ':00'
        df.set_index(pd.to_datetime(df.new_idx, errors='raise'), inplace=True)
        # append to list
        profiles_prjs.append(df)

    # concat into a single df and return
    ret = pd.concat(profiles_prjs).drop(['year','month','day','hour','new_idx'], axis=1)
    
    return ret

def preprocess_demand(db_dir, years, t_res):
    """Prepare demand data and and demand profiles for the model."""
    # 1. Import and interpolate demand data
    demands = pd.read_excel(f"{db_dir}//demand.xlsx", sheet_name="demands", index_col=0)
    drivers_prj = pd.read_excel(f"{db_dir}//demand.xlsx", sheet_name="drivers")
    demand_profiles = pd.read_excel(f"{db_dir}//demand.xlsx", sheet_name="normalized_profiles").set_index('time')

    # 2. Int/extrapolate demand drivers
    drivers_prj = int_extrapolate(drivers_prj, model_years=years)

    def project_demand(y, driver, start_value, base_year=years[0], dc=1):
        prj = start_value * (drivers_prj[drivers_prj.driver==driver][y].values[0]/drivers_prj[drivers_prj.driver==driver][base_year].values[0])**dc
        return prj

    # We want to use this function to create a dataframe with demand projections called dmd_prj, 
    # that is analogous to the dataframe yearly_demand from last week's model:
    dmd_prj = pd.DataFrame(index=demands.index, columns=years)
    for i in demands.index:
        dmd_prj.loc[i,:] = [
                            project_demand(y,  
                            driver=demands.loc[i,['Driver']].values[0],
                            start_value=demands.loc[i,['Start_value']].values[0],
                            dc=demands.loc[i,['Exponent']].values[0]) for y in years 
                        ]
    demand_profiles_prj = propagate_profiles(demand_profiles,model_years=years,t_res=t_res)
    for y in years:
        for i in demands.index:
            demand_profiles_prj.loc[str(y),i] *= dmd_prj.loc[i,y]

    # 5. set up multiindex
    demand_profiles_prj.set_index(pd.MultiIndex.from_arrays([demand_profiles_prj.index.year, 
                                                                demand_profiles_prj.index]), inplace=True)    
    return demands, demand_profiles_prj




def preprocess_supply(db_dir, years, t_res):
    """Prepare resources, resource parameters, and renewable profiles."""
    # From main_PSEUDO.py:
    # - import resources, their parameters, and renewable profiles;
    # - interpolate/extrapolate resource parameters;
    # - propagate renewable profiles to all periods.
    # 1. From database/supply import resources, their parameters and the renewable profiles
    resources = pd.read_excel(f"{db_dir}//supply.xlsx", sheet_name='resources')
    resources_pars = pd.read_excel(f"{db_dir}//supply.xlsx", sheet_name='resources_parameters')
    ren_profiles = pd.read_excel(f"{db_dir}//supply.xlsx", sheet_name='ren_profiles', index_col=0)

    # 2. Int/extrapolate the resource parameters so that they are defined in all periods
    resources_pars = int_extrapolate(resources_pars, model_years=years)

    # 3. Propagate renewable temporal profiles to all periods
    ren_profiles = propagate_profiles(ren_profiles, model_years=years, t_res=t_res)
    return resources, resources_pars, ren_profiles



def preprocess_technologies(db_dir, years, passenger_cars_cf):
    """Prepare static and dynamic technology parameters."""
    # From main_PSEUDO.py:
    # - read static and dynamic technology parameters;
    # - interpolate/extrapolate dynamic parameters;
    # - convert units to those expected by PyPSA.

    # 1. From database/technologies read all static and dynamic technology parameters
    techs_s = pd.read_excel(f"{db_dir}//technologies.xlsx", sheet_name='static_parameters', index_col=[0,1])
    techs_d = pd.read_excel(f"{db_dir}//technologies.xlsx", sheet_name='dynamic_parameters', index_col=[0,1])
    
    # 2. Int/extrapolate dynamic parameters so that they are defined in all periods 
    techs_d = int_extrapolate(techs_d, model_years=years)


    vom_rows = (techs_d.index.get_level_values('Parameter') == 'VOM')

    techs_d.loc[vom_rows, years] = (techs_d.loc[vom_rows, years].fillna(0.0))

    # 3. Fix all units of dynamic parameters

    # Cost components are in €/kW or €/kWh, but PyPSA expects them to be in €/MW or €/MWh 
    # --> if column Unit contains '/kW' or '/kWh', multiply the corresponding cost components by 1000
    techs_d.loc[techs_d['Unit'].str.contains('/kW'), years] *= 1e3
    techs_d['Unit'] = techs_d['Unit'].str.replace('/kW','/MW')

    # Transport efficiency is in km/MWh, but PyPSA expects it to be in Mkm/MWh (i.e. million km per MWh)
    techs_d.loc[techs_d['Unit'].str.contains('km'), years] *= 1e-6
    techs_d['Unit'] = techs_d['Unit'].str.replace('km','Mkm')

    # Transport capital costs are in €/car, and need to be converted in €/[unit of capacity].
    techs_d.loc[techs_d['Unit'].str.contains('/car'), years] *= 1e6/passenger_cars_cf
    techs_d['Unit'] = techs_d['Unit'].str.replace('/car','/Mkm/h')
    
    # 4. Read in tech constraints
    cn = pd.read_excel(f"{db_dir}//technologies.xlsx", sheet_name='capacity_constraints', index_col=[0,1])
    cn = cn.sort_index()

    return techs_s, techs_d, cn