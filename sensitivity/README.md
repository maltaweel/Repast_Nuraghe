# sensitivity

The harnesses of the Sobol sensitivity analyses of the model (`code/`), published so that the analyses can be repeated.
Their results are in [`outputs/sensitivity/`](../outputs/sensitivity/) (see that folder's README for the tables).

| folder | what it runs | results in |
|---|---|---|
| [sobol2/](sobol2/) | the Sobol analysis of the headline `MOST_REALISTIC_AUDITED_LIT_P10`: 26 factors, Saltelli N = 512, 14,336 evaluations x seeds 1-3 (43,008 whole-island runs); uses the code variant `code_variant` (`code/` + one config flag) | `outputs/sensitivity/sobol2/` |
| [coop_sobol/](coop_sobol/) | cooperation-model Sobol: 11 factors x the cooperation scenarios none / mixed / full, Saltelli N = 512, 19,968 evaluations (one seed each) | `outputs/sensitivity/coop_sobol/` |

## Path tokens

The scripts are the ones that produced the published results, with the local folders replaced by the tokens below (as in
`config/queue.tsv`) and the run-folder paths set to the layout below. Replace the tokens before running:

| token | meaning |
|---|---|
| `@RUN_DIR@` | a run folder holding the code, the configuration and the derived inputs (layout below) |
| `@WORK_DIR@` | the harness's own working folder (a copy of `sensitivity/sobol2/` or `sensitivity/coop_sobol/`); `design.csv`, `evals/` and `logs/` are written there |
| `@PYTHON@` | the Python interpreter (3.12+, with the packages of `code/requirements.txt`, SALib 1.6.0 and mpi4py) |
| `@PROJECT@` | only in `coop_sobol/analyse.py`: the folder of external stage-2 indices for an optional comparison column; not included, the column stays empty without them |

```
REPO=/path/to/Repast_Nuraghe  RUN=/path/to/run  WORK=/path/to/work/sobol2
cp -r $REPO/sensitivity/sobol2 $WORK && cd $WORK
sed -i "s#@RUN_DIR@#$RUN#g; s#@WORK_DIR@#$WORK#g; s#@PYTHON@#$(command -v python3)#g; s#@PROJECT@#$RUN#g" *.py *.sh
```

Layout of `@RUN_DIR@` (the run folder of the README's "Run the queue"):

```
code/                                       copy of code/ (coop_sobol)
code_variant/                               copy of code/ + sensitivity/sobol2/code_variant.patch (sobol2)
configs/config_full_audited.yaml            config/scenarios/config_full_audited.yaml with data_dir, paths.cache_dir
                                            and output_dir set to your folders
outputs/caches/config_full_audited/runs/    the engine-B runs of the queue (optional identity check of coop_sobol)
outputs/caches/config_full_audited_alt_stones7/
                                            a derived-input cache built with the stones7 stone rule (sobol2, factor
                                            stone_rule only)
```

The configuration the notebooks write after `notebooks/02_inputs.ipynb` (`WORK_DIR/config.yaml`, with the folders
already set) can be copied to `configs/config_full_audited.yaml`. The derived inputs are described in `data/derived/README.md`
(`python notebooks/fetch_data.py --rebuild-derived`; with `--stone-rule stones7` into a second folder for the stones7
cache, an equivalent build that has not been compared byte for byte with the run's cache).

## How these files relate to the runs

The scripts in `sensitivity/` are the harnesses of the run folders, with the paths replaced as above.
