# MAGNET Evaluation Card Visualization Trame App

## Quick Start
### (Preliminary) Populate Results 
From MAGNET, generate `results.json` by evaluating each card you would like to visualize. For example, you can use the `evaluate` command on our simple example card:
```
magnet evaluate magnet/cards/simple.yaml
```
The evaluation will automatically generate the directory structure below, creating a random card id for each `evaluate` call. 
```
magnet/cards/
├── evaluations
│   └── {card.id}
│       └── results.json
└── simple.yaml
```
This visualization app expects a path argument such as `'magnet/cards/evaluation'` to a directory of card ids with `results.json` contents. 

### Install dependencies
This is an intentionally lightweight visualization tool will minimal dependencies. 
```bash
uv venv --python 3.11 --seed .venv-311-evalcard-viz
source .venv-311-evalcard-viz/bin/activate
uv pip install .
```
Alternatively, you can extend your existing MAGNET environment by installing `trame` and `trame-vuetify`.

### Running the App
With results and environment ready, you can start the trame app and visualize your card runs.
```
python visualization.py ../aiq-magnet/magnet/cards/evaluations
```

## App Features

### Dashboard
The visualization app intentionally populates a library of cards that can be selected to render on the right-side focused view.
![Dashboard View](assets/dashboard.png)
A short catalog entry displays the title, description, category, number of sweeps/runs, and verfication rate. The focused view displays the raw python claim being resolved as well as all of the parameter sweep results.

Note: For this version, you may assume 100% Pass cards contain a VERIFIED claim, whereas others have been FALSIFIED. 

### Search for cards
There are three fields available to search for particular cards: title, category, and result.

As shown below, the Llama example card can be found by searching for its title in plain-text. However, the category and result fields could further narrow down particular evaluated claims. 
![Search](assets/search.png)

### Hide Details
Runs and symbols are both collapsable headings. You may click directly on 'Runs (X)' to hide all sweeps. Similarly, you may select the brackets icon next to 'Symbols' to hide the symbol-value pairs for all sweeps.

Using a falsified sweep for example,
![Llama Falsified Run](assets/falsified_sweep.png)

And after hiding the details:
![Llama Falsified Details Hidden](assets/falsified_sweep_toggled.png)



